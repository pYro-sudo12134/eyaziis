import psycopg2
from psycopg2.extras import DictCursor
from abc import ABC, abstractmethod
from datetime import datetime
from typing import List, Dict, Optional, Tuple
import json

class DatabaseConnection(ABC):
    @abstractmethod
    def get_connection(self):
        pass
    
    @abstractmethod
    def close(self):
        pass

class PostgreSQLConnection(DatabaseConnection):
    def __init__(self, host='localhost', dbname='postgres', 
                 user='postgres', password='postgres', port=5432):
        self.host = host
        self.dbname = dbname
        self.user = user
        self.password = password
        self.port = port
        self.connection = None
        self.connected = False
    
    def get_connection(self):
        if not self.connected:
            self.connect()
        return self.connection
    
    def connect(self):
        try:
            print("Подключение к PostgreSQL")
            
            self.connection = psycopg2.connect(
                host=self.host,
                dbname=self.dbname,
                user=self.user,
                password=self.password,
                port=self.port
            )
            
            self.connected = True
            print("Подключение установлено!")
            
            cursor = self.connection.cursor()
            cursor.execute("SET search_path TO public;")
            self.connection.commit()
            cursor.close()
            
        except Exception as e:
            print(f"Ошибка подключения: {e}")
            self.connected = False
            self.connection = None
            raise
    
    def close(self):
        if self.connection:
            self.connection.close()
            print("Соединение закрыто")
            self.connected = False

class CorpusDatabase:
    """Расширенный класс для работы с корпусом"""
    
    def __init__(self, connection: PostgreSQLConnection):
        self.conn = connection
        if not self.conn.connected:
            self.conn.connect()
        self.create_corpus_tables()
    
    def create_corpus_tables(self):
        """Создание таблиц для корпуса"""
        queries = [
            """
            CREATE TABLE IF NOT EXISTS public.documents (
                id SERIAL PRIMARY KEY,
                title VARCHAR(500) NOT NULL,
                filename VARCHAR(500),
                source VARCHAR(200),
                author VARCHAR(200),
                year INTEGER,
                genre VARCHAR(100),
                domain VARCHAR(100),
                language VARCHAR(50) DEFAULT 'russian',
                text_hash VARCHAR(64) UNIQUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS public.word_forms (
                id SERIAL PRIMARY KEY,
                word_form VARCHAR(255) UNIQUE NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS public.morphology (
                id SERIAL PRIMARY KEY,
                word_form_id INTEGER NOT NULL REFERENCES public.word_forms(id) ON DELETE CASCADE,
                part_of_speech VARCHAR(50),
                gender VARCHAR(20),
                number VARCHAR(20),
                case_form VARCHAR(20),
                normal_form VARCHAR(255),  -- Лемма (нормальная форма)
                confidence FLOAT,
                full_tag TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(word_form_id)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS public.sentences (
                id SERIAL PRIMARY KEY,
                document_id INTEGER NOT NULL REFERENCES public.documents(id) ON DELETE CASCADE,
                sentence_text TEXT NOT NULL,
                sentence_index INTEGER NOT NULL,
                word_count INTEGER,
                char_count INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS public.tokens (
                id SERIAL PRIMARY KEY,
                sentence_id INTEGER NOT NULL REFERENCES public.sentences(id) ON DELETE CASCADE,
                word_form_id INTEGER REFERENCES public.word_forms(id),
                token_text VARCHAR(255) NOT NULL,
                token_index INTEGER NOT NULL,
                is_punctuation BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS public.concordance (
                id SERIAL PRIMARY KEY,
                word_form_id INTEGER NOT NULL REFERENCES public.word_forms(id) ON DELETE CASCADE,
                sentence_id INTEGER NOT NULL REFERENCES public.sentences(id) ON DELETE CASCADE,
                left_context TEXT NOT NULL,
                keyword TEXT NOT NULL,
                right_context TEXT NOT NULL,
                full_sentence TEXT NOT NULL,
                document_id INTEGER REFERENCES public.documents(id) ON DELETE CASCADE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """,
            # Индексы
            """
            CREATE INDEX IF NOT EXISTS idx_documents_domain ON public.documents(domain)
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_documents_genre ON public.documents(genre)
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_sentences_document_id ON public.sentences(document_id)
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_tokens_sentence_id ON public.tokens(sentence_id)
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_tokens_word_form_id ON public.tokens(word_form_id)
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_concordance_word_form_id ON public.concordance(word_form_id)
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_concordance_sentence_id ON public.concordance(sentence_id)
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_morphology_word_form_id ON public.morphology(word_form_id)
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_morphology_part_of_speech ON public.morphology(part_of_speech)
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_morphology_normal_form ON public.morphology(normal_form)
            """
        ]
        
        cursor = self.conn.connection.cursor()
        for query in queries:
            try:
                cursor.execute(query)
            except Exception as e:
                print(f"Ошибка при выполнении запроса: {e}")
                print(f"Запрос: {query[:100]}...")
        self.conn.connection.commit()
        cursor.close()
        print("Таблицы корпуса созданы")
    
    def get_or_create_word_form(self, word_form: str) -> Optional[int]:
        """
        Получение ID словоформы или создание новой
        
        Args:
            word_form: словоформа
        
        Returns:
            ID словоформы или None в случае ошибки
        """
        select_query = """
            SELECT id FROM public.word_forms WHERE word_form = %s
        """
        
        try:
            cursor = self.conn.connection.cursor()
            cursor.execute(select_query, (word_form.lower(),))
            result = cursor.fetchone()
            
            if result:
                cursor.close()
                return result[0]
            
            # Создаем новую словоформу
            insert_query = """
                INSERT INTO public.word_forms (word_form)
                VALUES (%s)
                RETURNING id
            """
            cursor.execute(insert_query, (word_form.lower(),))
            word_form_id = cursor.fetchone()[0]
            self.conn.connection.commit()
            cursor.close()
            return word_form_id
            
        except Exception as e:
            print(f"Ошибка получения/создания словоформы: {e}")
            return None

    def add_morphology(self, word_form_id: int, morphology_data: Dict) -> bool:
        """
        Добавление морфологической информации для словоформы
        
        Args:
            word_form_id: ID словоформы
            morphology_data: словарь с морфологическими признаками
        
        Returns:
            True в случае успеха, False при ошибке
        """
        query = """
            INSERT INTO public.morphology 
            (word_form_id, part_of_speech, gender, number, case_form, normal_form, confidence, full_tag)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (word_form_id) 
            DO UPDATE SET
                part_of_speech = EXCLUDED.part_of_speech,
                gender = EXCLUDED.gender,
                number = EXCLUDED.number,
                case_form = EXCLUDED.case_form,
                normal_form = EXCLUDED.normal_form,
                confidence = EXCLUDED.confidence,
                full_tag = EXCLUDED.full_tag,
                created_at = CURRENT_TIMESTAMP
        """
        
        try:
            cursor = self.conn.connection.cursor()
            cursor.execute(query, (
                word_form_id,
                morphology_data.get('part_of_speech'),
                morphology_data.get('gender'),
                morphology_data.get('number'),
                morphology_data.get('case_form'),
                morphology_data.get('normal_form'),
                morphology_data.get('confidence', 0.0),
                morphology_data.get('tag')
            ))
            self.conn.connection.commit()
            cursor.close()
            return True
        except Exception as e:
            print(f"Ошибка добавления морфологии: {e}")
            self.conn.connection.rollback()
            return False

    def add_document(self, title: str, filename: str = None, source: str = None,
                    author: str = None, year: int = None, genre: str = None,
                    domain: str = 'animals', text_hash: str = None) -> Optional[int]:
        """Добавление документа в корпус"""
        
        if text_hash:
            check_query = "SELECT id FROM public.documents WHERE text_hash = %s"
            try:
                cursor = self.conn.connection.cursor()
                cursor.execute(check_query, (text_hash,))
                existing = cursor.fetchone()
                if existing:
                    print(f"Документ с хешем {text_hash[:8]}... уже существует (ID: {existing[0]})")
                    cursor.close()
                    return existing[0]
                cursor.close()
            except Exception as e:
                print(f"Ошибка при проверке существующего документа: {e}")
        
        query = """
            INSERT INTO public.documents 
            (title, filename, source, author, year, genre, domain, text_hash)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (text_hash) DO UPDATE SET
                title = EXCLUDED.title,
                filename = EXCLUDED.filename,
                source = EXCLUDED.source,
                author = EXCLUDED.author,
                year = EXCLUDED.year,
                genre = EXCLUDED.genre,
                updated_at = CURRENT_TIMESTAMP
            RETURNING id
        """
        
        try:
            cursor = self.conn.connection.cursor()
            cursor.execute(query, (title, filename, source, author, year, genre, domain, text_hash))
            doc_id = cursor.fetchone()[0]
            self.conn.connection.commit()
            cursor.close()
            return doc_id
        except Exception as e:
            print(f"Ошибка добавления документа: {e}")
            self.conn.connection.rollback()
            return None
    
    def add_sentence(self, document_id: int, sentence_text: str, 
                    sentence_index: int) -> Optional[int]:
        """Добавление предложения"""
        word_count = len(sentence_text.split())
        char_count = len(sentence_text)
        
        query = """
            INSERT INTO public.sentences 
            (document_id, sentence_text, sentence_index, word_count, char_count)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id
        """
        
        try:
            cursor = self.conn.connection.cursor()
            cursor.execute(query, (document_id, sentence_text, sentence_index, 
                                  word_count, char_count))
            sentence_id = cursor.fetchone()[0]
            self.conn.connection.commit()
            cursor.close()
            return sentence_id
        except Exception as e:
            print(f"Ошибка добавления предложения: {e}")
            return None
    
    def add_token(self, sentence_id: int, word_form_id: Optional[int], 
                token_text: str, token_index: int, is_punctuation: bool = False) -> Optional[int]:
        """Добавление токена"""
        query = """
            INSERT INTO public.tokens 
            (sentence_id, word_form_id, token_text, token_index, is_punctuation)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id
        """
        
        try:
            cursor = self.conn.connection.cursor()
            cursor.execute(query, (sentence_id, word_form_id, token_text, 
                                token_index, is_punctuation))
            token_id = cursor.fetchone()[0]
            self.conn.connection.commit()
            cursor.close()
            return token_id
        except Exception as e:
            print(f"Ошибка добавления токена: {e}")
            self.conn.connection.rollback()
            return None
    
    def add_concordance_entry(self, word_form_id: int, sentence_id: int,
                             left_context: str, keyword: str, right_context: str,
                             full_sentence: str, document_id: int) -> bool:
        """Добавление записи в конкорданс"""
        query = """
            INSERT INTO public.concordance 
            (word_form_id, sentence_id, left_context, keyword, right_context, 
             full_sentence, document_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """
        
        try:
            cursor = self.conn.connection.cursor()
            cursor.execute(query, (word_form_id, sentence_id, left_context, 
                                  keyword, right_context, full_sentence, document_id))
            self.conn.connection.commit()
            cursor.close()
            return True
        except Exception as e:
            print(f"Ошибка добавления в конкорданс: {e}")
            return False
    
    def search_concordance(self, word: str, context_size: int = 5, 
                          limit: int = 100) -> List[Dict]:
        """Поиск по конкордансу"""
        query = """
            SELECT c.left_context, c.keyword, c.right_context, 
                   c.full_sentence, d.title as document_title
            FROM public.concordance c
            JOIN public.word_forms wf ON c.word_form_id = wf.id
            JOIN public.documents d ON c.document_id = d.id
            WHERE wf.word_form = %s
            ORDER BY c.created_at
            LIMIT %s
        """
        
        try:
            cursor = self.conn.connection.cursor(cursor_factory=DictCursor)
            cursor.execute(query, (word, limit))
            results = []
            for row in cursor.fetchall():
                results.append({
                    'left_context': row['left_context'],
                    'keyword': row['keyword'],
                    'right_context': row['right_context'],
                    'full_sentence': row['full_sentence'],
                    'document_title': row['document_title']
                })
            cursor.close()
            return results
        except Exception as e:
            print(f"Ошибка поиска в конкордансе: {e}")
            return []
    
    def get_word_frequency_by_domain(self, domain: str = 'animals', 
                                     limit: int = 50) -> List[Tuple]:
        """Частотность слов по предметной области"""
        query = """
            SELECT wf.word_form, COUNT(*) as freq
            FROM public.tokens t
            JOIN public.sentences s ON t.sentence_id = s.id
            JOIN public.documents d ON s.document_id = d.id
            JOIN public.word_forms wf ON t.word_form_id = wf.id
            WHERE d.domain = %s AND t.is_punctuation = FALSE
            GROUP BY wf.word_form
            ORDER BY freq DESC
            LIMIT %s
        """
        
        try:
            cursor = self.conn.connection.cursor()
            cursor.execute(query, (domain, limit))
            results = cursor.fetchall()
            cursor.close()
            return results
        except Exception as e:
            print(f"Ошибка получения частотности: {e}")
            return []
    
    def get_morphology_statistics(self, domain: str = 'animals') -> Dict:
        """Статистика по морфологическим категориям"""
        stats = {}
        
        queries = {
            'part_of_speech': """
                SELECT m.part_of_speech, COUNT(*) as count
                FROM public.morphology m
                JOIN public.word_forms wf ON m.word_form_id = wf.id
                JOIN public.tokens t ON wf.id = t.word_form_id
                JOIN public.sentences s ON t.sentence_id = s.id
                JOIN public.documents d ON s.document_id = d.id
                WHERE d.domain = %s AND m.part_of_speech IS NOT NULL
                GROUP BY m.part_of_speech
                ORDER BY count DESC
            """,
            'gender': """
                SELECT m.gender, COUNT(*) as count
                FROM public.morphology m
                JOIN public.word_forms wf ON m.word_form_id = wf.id
                JOIN public.tokens t ON wf.id = t.word_form_id
                JOIN public.sentences s ON t.sentence_id = s.id
                JOIN public.documents d ON s.document_id = d.id
                WHERE d.domain = %s AND m.gender IS NOT NULL
                GROUP BY m.gender
                ORDER BY count DESC
            """,
            'number': """
                SELECT m.number, COUNT(*) as count
                FROM public.morphology m
                JOIN public.word_forms wf ON m.word_form_id = wf.id
                JOIN public.tokens t ON wf.id = t.word_form_id
                JOIN public.sentences s ON t.sentence_id = s.id
                JOIN public.documents d ON s.document_id = d.id
                WHERE d.domain = %s AND m.number IS NOT NULL
                GROUP BY m.number
                ORDER BY count DESC
            """,
            'case': """
                SELECT m.case_form, COUNT(*) as count
                FROM public.morphology m
                JOIN public.word_forms wf ON m.word_form_id = wf.id
                JOIN public.tokens t ON wf.id = t.word_form_id
                JOIN public.sentences s ON t.sentence_id = s.id
                JOIN public.documents d ON s.document_id = d.id
                WHERE d.domain = %s AND m.case_form IS NOT NULL
                GROUP BY m.case_form
                ORDER BY count DESC
            """
        }
        
        try:
            cursor = self.conn.connection.cursor()
            for stat_name, query in queries.items():
                cursor.execute(query, (domain,))
                stats[stat_name] = cursor.fetchall()
            cursor.close()
        except Exception as e:
            print(f"Ошибка получения статистики: {e}")
        
        return stats
    
    def get_documents_list(self, domain: str = 'animals') -> List[Dict]:
        """Список документов в корпусе"""
        query = """
            SELECT id, title, author, year, genre, source, 
                   created_at, 
                   (SELECT COUNT(*) FROM public.sentences WHERE document_id = d.id) as sentence_count
            FROM public.documents d
            WHERE domain = %s
            ORDER BY created_at DESC
        """
        
        try:
            cursor = self.conn.connection.cursor(cursor_factory=DictCursor)
            cursor.execute(query, (domain,))
            results = [dict(row) for row in cursor.fetchall()]
            cursor.close()
            return results
        except Exception as e:
            print(f"Ошибка получения списка документов: {e}")
            return []
    
    def search_by_word_form(self, word_form: str, domain: str = 'animals') -> List[Dict]:
        """Поиск предложений по словоформе"""
        query = """
            SELECT s.sentence_text, d.title as document_title, 
                t.token_index, m.normal_form as lemma
            FROM public.tokens t
            JOIN public.sentences s ON t.sentence_id = s.id
            JOIN public.documents d ON s.document_id = d.id
            JOIN public.word_forms wf ON t.word_form_id = wf.id
            LEFT JOIN public.morphology m ON wf.id = m.word_form_id
            WHERE wf.word_form = %s AND d.domain = %s
            ORDER BY d.title, s.sentence_index, t.token_index
            LIMIT 500
        """
        
        try:
            cursor = self.conn.connection.cursor(cursor_factory=DictCursor)
            cursor.execute(query, (word_form, domain))
            results = []
            for row in cursor.fetchall():
                results.append({
                    'sentence_text': row['sentence_text'],
                    'document_title': row['document_title'],
                    'token_index': row['token_index'],
                    'lemma': row['lemma']
                })
            cursor.close()
            return results
        except Exception as e:
            print(f"Ошибка поиска по словоформе: {e}")
            return []
    
    def search_by_lemma(self, lemma: str, domain: str = 'animals') -> List[Dict]:
        query = """
            SELECT s.sentence_text, d.title as document_title, 
                t.token_text, m.normal_form as lemma
            FROM public.tokens t
            JOIN public.sentences s ON t.sentence_id = s.id
            JOIN public.documents d ON s.document_id = d.id
            JOIN public.word_forms wf ON t.word_form_id = wf.id
            JOIN public.morphology m ON wf.id = m.word_form_id
            WHERE m.normal_form = %s AND d.domain = %s
            ORDER BY d.title, s.sentence_index, t.token_index
            LIMIT 500
        """
        
        try:
            cursor = self.conn.connection.cursor(cursor_factory=DictCursor)
            cursor.execute(query, (lemma, domain))
            results = [dict(row) for row in cursor.fetchall()]
            cursor.close()
            return results
        except Exception as e:
            print(f"Ошибка поиска по лемме: {e}")
            return []
    
    def search_by_morphology(self, part_of_speech: str = None, gender: str = None,
                            number: str = None, case: str = None,
                            domain: str = 'animals') -> List[Dict]:
        """Поиск по морфологическим признакам"""
        conditions = ["d.domain = %s"]
        params = [domain]
        
        if part_of_speech and part_of_speech.strip():
            conditions.append("m.part_of_speech = %s")
            params.append(part_of_speech)
        if gender and gender.strip():
            conditions.append("m.gender = %s")
            params.append(gender)
        if number and number.strip():
            conditions.append("m.number = %s")
            params.append(number)
        if case and case.strip():
            conditions.append("m.case_form = %s")
            params.append(case)
        
        where_clause = " AND ".join(conditions)
        
        query = f"""
            SELECT DISTINCT s.sentence_text, d.title as document_title, 
                t.token_text, wf.word_form,
                m.part_of_speech, m.gender, m.number, m.case_form,
                d.title as sort_title, s.sentence_index as sort_index
            FROM public.tokens t
            JOIN public.sentences s ON t.sentence_id = s.id
            JOIN public.documents d ON s.document_id = d.id
            JOIN public.word_forms wf ON t.word_form_id = wf.id
            JOIN public.morphology m ON wf.id = m.word_form_id
            WHERE {where_clause}
            ORDER BY sort_title, sort_index
            LIMIT 500
        """
        
        try:
            cursor = self.conn.connection.cursor(cursor_factory=DictCursor)
            cursor.execute(query, params)
            results = []
            seen = set()
            
            for row in cursor.fetchall():
                key = (row['sentence_text'], row['token_text'], row['word_form'])
                if key not in seen:
                    seen.add(key)
                    results.append({
                        'sentence_text': row['sentence_text'],
                        'document_title': row['document_title'],
                        'token_text': row['token_text'],
                        'word_form': row['word_form'],
                        'part_of_speech': row['part_of_speech'],
                        'gender': row['gender'],
                        'number': row['number'],
                        'case_form': row['case_form']
                    })
            
            cursor.close()
            return results
        except Exception as e:
            print(f"Ошибка поиска по морфологии: {e}")
            return []