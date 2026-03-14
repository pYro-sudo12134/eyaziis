import os
import re
import hashlib
from typing import List, Dict, Optional, Tuple
from datetime import datetime
import nltk
from psycopg2.extras import DictCursor
from nltk.tokenize import sent_tokenize, word_tokenize
import warnings
warnings.filterwarnings('ignore')

from database import CorpusDatabase, PostgreSQLConnection
from text_processor import (
    TXTReaderStrategy, RTFReaderStrategy, 
    PDFReaderStrategy, DOCXReaderStrategy, DOCReaderStrategy
)
from morphology_analyzer import get_morphology_analyzer
from syntax_analyzer import get_syntax_analyzer

class CorpusManager:
    """Корпусный менеджер для работы с коллекцией текстов"""
    
    def __init__(self, db_connection: PostgreSQLConnection):
        self.db = CorpusDatabase(db_connection)
        self.morph_analyzer = get_morphology_analyzer()
        
        self.txt_reader = TXTReaderStrategy()
        self.rtf_reader = RTFReaderStrategy()
        self.pdf_reader = PDFReaderStrategy()
        self.docx_reader = DOCXReaderStrategy()
        self.doc_reader = DOCReaderStrategy()
        
        try:
            nltk.data.find('tokenizers/punkt')
        except LookupError:
            nltk.download('punkt', quiet=True)
    
    def _get_reader_strategy(self, file_path):
        """Определение стратегии чтения по расширению файла"""
        ext = file_path.lower()
        if ext.endswith('.txt'):
            return self.txt_reader
        elif ext.endswith('.rtf'):
            return self.rtf_reader
        elif ext.endswith('.pdf'):
            return self.pdf_reader
        elif ext.endswith('.docx'):
            return self.docx_reader
        elif ext.endswith('.doc'):
            return self.doc_reader
        else:
            return None
    
    def process_document(self, file_path: str, metadata: Dict) -> Dict:
        """
        Обработка документа и добавление в корпус
        
        Args:
            file_path: путь к файлу
            metadata: метаданные документа (title, author, year, genre, source)
        
        Returns:
            Dict с результатами обработки
        """
        results = {
            'success': False,
            'document_id': None,
            'sentences_count': 0,
            'tokens_count': 0,
            'errors': []
        }
        
        try:
            reader = self._get_reader_strategy(file_path)
            
            if not reader:
                results['errors'].append(f"Неподдерживаемый формат: {file_path}")
                return results
            
            print(f"Чтение файла {file_path}...")
            text = reader.read(file_path)
            
            if not text or not text.strip():
                results['errors'].append("Файл пуст или не содержит текста")
                return results
            
            print(f"Текст прочитан, длина: {len(text)} символов")
            
            text_hash = hashlib.sha256(text.encode('utf-8')).hexdigest()
            
            doc_id = self.db.add_document(
                title=metadata.get('title', os.path.basename(file_path)),
                filename=os.path.basename(file_path),
                source=metadata.get('source'),
                author=metadata.get('author'),
                year=metadata.get('year'),
                genre=metadata.get('genre'),
                domain='animals',
                text_hash=text_hash
            )
            
            if not doc_id:
                results['errors'].append("Не удалось создать документ")
                return results
            
            results['document_id'] = doc_id
            
            print("Токенизация на предложения...")
            sentences = sent_tokenize(text, language='russian')
            print(f"Найдено {len(sentences)} предложений")
            
            for sent_idx, sentence in enumerate(sentences):
                if not sentence.strip():
                    continue
                
                sentence_id = self.db.add_sentence(doc_id, sentence.strip(), sent_idx)
                
                if not sentence_id:
                    continue
                
                results['sentences_count'] += 1
                words = word_tokenize(sentence, language='russian')
                
                for token_idx, token in enumerate(words):
                    is_punctuation = not bool(re.match(r'[а-яёА-ЯЁ]+', token))
                    word_form_id = self._get_word_form_id(token)
                    
                    self.db.add_token(
                        sentence_id=sentence_id,
                        word_form_id=word_form_id,
                        token_text=token,
                        token_index=token_idx,
                        is_punctuation=is_punctuation
                    )
                    
                    results['tokens_count'] += 1
                    
                    if word_form_id and not is_punctuation:
                        self._create_concordance_entry(
                            word_form_id, sentence_id, token, 
                            sentence, token_idx, doc_id
                        )
            
            results['success'] = True
            print(f"Документ обработан успешно: {results['sentences_count']} предложений, {results['tokens_count']} токенов")
            
        except Exception as e:
            results['errors'].append(str(e))
            print(f"Ошибка обработки документа: {e}")
            import traceback
            traceback.print_exc()
        
        return results
    
    def _get_word_form_id(self, token: str) -> Optional[int]:
        """Получение ID словоформы из базы или создание новой"""
        word_form_id = self.db.get_or_create_word_form(token)
        
        if word_form_id:
            analysis = self.morph_analyzer.analyze_word(token)
            if analysis and analysis.get('confidence', 0) > 0.3:
                self.db.add_morphology(word_form_id, analysis)
        
        return word_form_id
    
    def _create_concordance_entry(self, word_form_id: int, sentence_id: int,
                                  keyword: str, sentence: str, 
                                  token_idx: int, doc_id: int):
        """Создание записи в конкордансе"""
        words = sentence.split()
        
        left_start = max(0, token_idx - 5)
        right_end = min(len(words), token_idx + 6)
        
        left_context = ' '.join(words[left_start:token_idx])
        right_context = ' '.join(words[token_idx + 1:right_end])
        
        self.db.add_concordance_entry(
            word_form_id=word_form_id,
            sentence_id=sentence_id,
            left_context=left_context,
            keyword=keyword,
            right_context=right_context,
            full_sentence=sentence,
            document_id=doc_id
        )
    
    def search(self, query: str, search_type: str = 'word_form', filters: Dict = None) -> Dict:
        """
        Поиск в корпусе
        
        Args:
            query: поисковый запрос
            search_type: тип поиска (word_form, lemma, morphology, concordance, semantic)
            filters: фильтры (domain, genre, author, year_from, year_to)
        
        Returns:
            Dict с результатами поиска
        """
        results = {
            'query': query,
            'type': search_type,
            'total': 0,
            'items': [],
            'filters': filters or {}
        }
        
        domain = filters.get('domain', 'animals') if filters else 'animals'
        
        try:
            if search_type == 'word_form':
                items = self.db.search_by_word_form(query, domain)
                results['items'] = items
                results['total'] = len(items)
                
            elif search_type == 'lemma':
                items = self.db.search_by_lemma(query, domain)
                results['items'] = items
                results['total'] = len(items)
                
            elif search_type == 'concordance':
                items = self.db.search_concordance(query, context_size=5, limit=200)
                results['items'] = items
                results['total'] = len(items)
                
            elif search_type == 'morphology':
                params = self._parse_morphology_query(query)
                items = self.db.search_by_morphology(
                    part_of_speech=params.get('pos'),
                    gender=params.get('gender'),
                    number=params.get('number'),
                    case=params.get('case'),
                    domain=domain
                )
                results['items'] = items
                results['total'] = len(items)
                
            elif search_type == 'semantic':
                # НОВЫЙ ТИП ПОИСКА
                items = self.semantic_search(query, domain)
                results['items'] = items.get('items', [])
                results['total'] = items.get('total', 0)
        
        except Exception as e:
            results['error'] = str(e)
            print(f"Ошибка поиска: {e}")
            import traceback
            traceback.print_exc()
        
        return results
    
    def _parse_morphology_query(self, query: str) -> Dict:
        """Парсинг морфологического запроса"""
        params = {}
        parts = query.split('&')
        
        for part in parts:
            if '=' in part:
                key, value = part.split('=', 1)
                params[key.strip()] = value.strip()
        
        return params
    
    def get_statistics(self, domain: str = 'animals') -> Dict:
        """Получение статистики по корпусу"""
        stats = {
            'domain': domain,
            'documents': 0,
            'sentences': 0,
            'tokens': 0,
            'unique_words': 0,
            'morphology': {},
            'frequent_words': []
        }
        
        try:
            cursor = self.db.conn.connection.cursor()
            
            cursor.execute("SELECT COUNT(*) FROM public.documents WHERE domain = %s", (domain,))
            stats['documents'] = cursor.fetchone()[0]
            
            cursor.execute("""
                SELECT COUNT(*) FROM public.sentences s
                JOIN public.documents d ON s.document_id = d.id
                WHERE d.domain = %s
            """, (domain,))
            stats['sentences'] = cursor.fetchone()[0]
            
            cursor.execute("""
                SELECT COUNT(*) FROM public.tokens t
                JOIN public.sentences s ON t.sentence_id = s.id
                JOIN public.documents d ON s.document_id = d.id
                WHERE d.domain = %s AND t.is_punctuation = FALSE
            """, (domain,))
            stats['tokens'] = cursor.fetchone()[0]
            
            cursor.execute("""
                SELECT COUNT(DISTINCT m.normal_form) 
                FROM public.tokens t
                JOIN public.sentences s ON t.sentence_id = s.id
                JOIN public.documents d ON s.document_id = d.id
                JOIN public.word_forms wf ON t.word_form_id = wf.id
                JOIN public.morphology m ON wf.id = m.word_form_id
                WHERE d.domain = %s AND m.normal_form IS NOT NULL
            """, (domain,))
            stats['unique_words'] = cursor.fetchone()[0]
            
            cursor.close()
            
            stats['morphology'] = self.db.get_morphology_statistics(domain)
            stats['frequent_words'] = self.db.get_word_frequency_by_domain(domain, 50)
            
        except Exception as e:
            print(f"Ошибка получения статистики: {e}")
        
        return stats
    
    def get_concordance(self, word: str, context_size: int = 5) -> List[Dict]:
        """Получение конкорданса для слова"""
        return self.db.search_concordance(word, context_size)
    
    def get_documents(self, domain: str = 'animals') -> List[Dict]:
        """Получение списка документов"""
        return self.db.get_documents_list(domain)
    
    def export_corpus_stats(self, format: str = 'json') -> Dict:
        """Экспорт статистики корпуса"""
        stats = self.get_statistics()
        
        if format == 'json':
            return stats
        else:
            return stats
        
    def semantic_search(self, query: str, domain: str = 'animals') -> Dict:
        """
        Семантический поиск по ключевым словам (упрощенная версия)
        Ищет предложения, содержащие все слова из запроса или их формы
        
        Args:
            query: поисковый запрос (несколько слов через пробел)
            domain: предметная область
        
        Returns:
            Dict с результатами поиска
        """
        results = {
            'query': query,
            'type': 'semantic',
            'total': 0,
            'items': [],
            'filters': {'domain': domain}
        }
        
        try:
            # Разбиваем запрос на слова
            words = query.lower().split()
            if not words:
                return results
            
            # Получаем леммы для каждого слова запроса
            lemmas = []
            for word in words:
                analysis = self.morph_analyzer.analyze_word(word)
                if analysis and analysis.get('normal_form'):
                    lemmas.append(analysis['normal_form'])
                else:
                    lemmas.append(word)
            
            print(f"Семантический поиск: слова={words}, леммы={lemmas}")
            
            # Строим запрос для поиска предложений, содержащих все леммы
            cursor = self.db.conn.connection.cursor(cursor_factory=DictCursor)
            
            # Сложный запрос для поиска предложений, содержащих все слова
            placeholders = ','.join(['%s'] * len(lemmas))
            
            query_sql = f"""
                WITH matched_sentences AS (
                    SELECT s.id, s.sentence_text, s.document_id,
                        COUNT(DISTINCT m.normal_form) as matched_words
                    FROM public.sentences s
                    JOIN public.tokens t ON s.id = t.sentence_id
                    JOIN public.word_forms wf ON t.word_form_id = wf.id
                    JOIN public.morphology m ON wf.id = m.word_form_id
                    WHERE m.normal_form IN ({placeholders})
                    AND t.is_punctuation = FALSE
                    GROUP BY s.id, s.sentence_text, s.document_id
                    HAVING COUNT(DISTINCT m.normal_form) = %s
                )
                SELECT ms.sentence_text, ms.id as sentence_id,
                    d.title as document_title,
                    d.id as document_id,
                    ms.matched_words
                FROM matched_sentences ms
                JOIN public.documents d ON ms.document_id = d.id
                WHERE d.domain = %s
                ORDER BY ms.matched_words DESC
                LIMIT 100
            """
            
            params = lemmas + [len(lemmas), domain]
            cursor.execute(query_sql, params)
            
            items = []
            for row in cursor.fetchall():
                items.append({
                    'sentence_text': row['sentence_text'],
                    'sentence_id': row['sentence_id'],
                    'document_title': row['document_title'],
                    'document_id': row['document_id'],
                    'matched_words': row['matched_words'],
                    'relevance': row['matched_words'] / len(lemmas)  # релевантность
                })
            
            cursor.close()
            
            results['items'] = items
            results['total'] = len(items)
            
        except Exception as e:
            results['error'] = str(e)
            print(f"Ошибка семантического поиска: {e}")
            import traceback
            traceback.print_exc()
        
        return results

    def analyze_sentence_syntax(self, sentence_id: int, sentence_text: str) -> Dict:
        """
        Синтаксический анализ одного предложения
        """
        try:
            # Получаем анализатор
            syntax_analyzer = get_syntax_analyzer()
            
            # Выполняем разбор
            parse_result = syntax_analyzer.parse_sentence(sentence_text, sentence_id)
            
            # Получаем соответствие между индексами spaCy и ID токенов в БД
            cursor = self.db.conn.connection.cursor(cursor_factory=DictCursor)
            cursor.execute("""
                SELECT id, token_index 
                FROM public.tokens 
                WHERE sentence_id = %s 
                ORDER BY token_index
            """, (sentence_id,))
            token_mapping = {row['token_index']: row['id'] for row in cursor.fetchall()}
            cursor.close()
            
            # Сохраняем дерево разбора
            self.db.save_parse_tree(sentence_id, parse_result, 'spacy')
            
            # Сохраняем отношения
            for rel in parse_result['relations']:
                if rel['head_id'] in token_mapping and rel['dependent_id'] in token_mapping:
                    self.db.add_syntax_relation(
                        sentence_id=sentence_id,
                        head_token_id=token_mapping[rel['head_id']],
                        dependent_token_id=token_mapping[rel['dependent_id']],
                        relation_type=rel['relation_type'],
                        relation_name=rel.get('relation_name', rel['relation_type']),
                        confidence=rel.get('confidence', 1.0)
                    )
            
            # Сохраняем члены предложения
            for part_type, items in parse_result['sentence_parts'].items():
                for item in items:
                    if item['token_id'] in token_mapping:
                        self.db.add_sentence_part(
                            sentence_id=sentence_id,
                            token_id=token_mapping[item['token_id']],
                            part_type=part_type,
                            part_name=item.get('relation_type', part_type),
                            head_of_group=(item.get('head_id') == item['token_id'])
                        )
            
            # СОХРАНЯЕМ СИНТАКСИЧЕСКИЕ ГРУППЫ
            group_counter = 0
            for group_type, groups in parse_result['groups'].items():
                for group in groups:
                    # Определяем тип группы
                    if 'noun_phrases' in group_type:
                        db_group_type = 'NP'
                    elif 'verb_phrases' in group_type:
                        db_group_type = 'VP'
                    elif 'prepositional_phrases' in group_type:
                        db_group_type = 'PP'
                    else:
                        db_group_type = 'OTHER'
                    
                    # Находим индексы начала и конца группы
                    if 'start' in group and 'end' in group:
                        start_idx = group['start']
                        end_idx = group['end']
                    elif 'head_id' in group:
                        # Если нет явных индексов, используем позицию главного слова
                        head_token = next((t for t in parse_result['tokens'] if t['id'] == group.get('head_id', 0)), None)
                        if head_token:
                            start_idx = max(0, head_token['id'] - 2)
                            end_idx = min(len(parse_result['tokens']) - 1, head_token['id'] + 2)
                        else:
                            continue
                    else:
                        continue
                    
                    # Находим ID главного слова
                    head_token_id = None
                    if 'head_id' in group and group['head_id'] in token_mapping:
                        head_token_id = token_mapping[group['head_id']]
                    elif 'root_id' in group and group['root_id'] in token_mapping:
                        head_token_id = token_mapping[group['root_id']]
                    
                    # Сохраняем группу
                    group_id = self.db.add_syntax_group(
                        sentence_id=sentence_id,
                        group_type=db_group_type,
                        head_token_id=head_token_id,
                        start_index=start_idx,
                        end_index=end_idx
                    )
                    
                    if group_id:
                        group_counter += 1
            
            print(f"  Сохранено групп: {group_counter}")
            return parse_result
            
        except Exception as e:
            print(f"Ошибка синтаксического анализа предложения {sentence_id}: {e}")
            import traceback
            traceback.print_exc()
            return {'error': str(e)}

    def analyze_document_syntax(self, document_id: int) -> Dict:
        """
        Синтаксический анализ всех предложений документа
        
        Args:
            document_id: ID документа
        
        Returns:
            Dict со статистикой анализа
        """
        results = {
            'document_id': document_id,
            'total_sentences': 0,
            'analyzed': 0,
            'failed': 0,
            'errors': []
        }
        
        try:
            # Получаем все предложения документа
            cursor = self.db.conn.connection.cursor(cursor_factory=DictCursor)
            cursor.execute("""
                SELECT id, sentence_text 
                FROM public.sentences 
                WHERE document_id = %s 
                ORDER BY sentence_index
            """, (document_id,))
            
            sentences = cursor.fetchall()
            cursor.close()
            
            results['total_sentences'] = len(sentences)
            
            # Анализируем каждое предложение
            for row in sentences:
                try:
                    self.analyze_sentence_syntax(row['id'], row['sentence_text'])
                    results['analyzed'] += 1
                    print(f"  ✓ Предложение {row['id']} проанализировано")
                except Exception as e:
                    results['failed'] += 1
                    results['errors'].append(f"Предложение {row['id']}: {str(e)}")
                    print(f"  ✗ Ошибка в предложении {row['id']}: {e}")
            
            print(f"Анализ документа {document_id} завершен: {results['analyzed']}/{results['total_sentences']}")
            
        except Exception as e:
            results['errors'].append(str(e))
            print(f"Ошибка анализа документа: {e}")
        
        return results

    def get_sentence_syntax(self, sentence_id: int) -> Dict:
        """
        Получение синтаксической информации о предложении из БД
        
        Args:
            sentence_id: ID предложения
        
        Returns:
            Dict с синтаксической информацией
        """
        return self.db.get_sentence_syntax(sentence_id)

    def search_by_syntax(self, pattern: Dict, domain: str = 'animals') -> List[Dict]:
        """
        Поиск по синтаксическому шаблону
        
        Args:
            pattern: шаблон поиска
            domain: предметная область
        
        Returns:
            Список результатов
        """
        return self.db.search_by_syntax_pattern(pattern, domain)

    def get_syntax_statistics(self, domain: str = 'animals') -> Dict:
        """
        Получение статистики по синтаксическому анализу
        
        Args:
            domain: предметная область
        
        Returns:
            Dict со статистикой
        """
        return self.db.get_syntax_statistics(domain)