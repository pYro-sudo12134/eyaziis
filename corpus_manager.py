import os
import re
import hashlib
from typing import List, Dict, Optional, Tuple
from datetime import datetime
import nltk
from nltk.tokenize import sent_tokenize, word_tokenize
import warnings
warnings.filterwarnings('ignore')

from database import CorpusDatabase, PostgreSQLConnection
from text_processor import (
    TXTReaderStrategy, RTFReaderStrategy, 
    PDFReaderStrategy, DOCXReaderStrategy, DOCReaderStrategy
)
from morphology_analyzer import get_morphology_analyzer


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
            search_type: тип поиска (word_form, lemma, morphology, concordance)
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
        
        except Exception as e:
            results['error'] = str(e)
            print(f"Ошибка поиска: {e}")
        
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