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
        self.create_syntax_tables()
    
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
                normal_form VARCHAR(255),
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
                syntax_analyzed BOOLEAN DEFAULT FALSE,
                syntax_analyzed_at TIMESTAMP,
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
    
    def create_syntax_tables(self):
        """Создание таблиц для синтаксического анализа"""
        queries = [
            """
            CREATE TABLE IF NOT EXISTS public.syntax_relations (
                id SERIAL PRIMARY KEY,
                sentence_id INTEGER NOT NULL REFERENCES public.sentences(id) ON DELETE CASCADE,
                head_token_id INTEGER NOT NULL REFERENCES public.tokens(id) ON DELETE CASCADE,
                dependent_token_id INTEGER NOT NULL REFERENCES public.tokens(id) ON DELETE CASCADE,
                relation_type VARCHAR(50) NOT NULL,  -- nsubj, obj, amod, etc.
                relation_name VARCHAR(100),           -- подлежащее, дополнение и т.д.
                confidence FLOAT DEFAULT 1.0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(sentence_id, head_token_id, dependent_token_id)
            )
            """,
            
            """
            CREATE TABLE IF NOT EXISTS public.parse_trees (
                id SERIAL PRIMARY KEY,
                sentence_id INTEGER NOT NULL REFERENCES public.sentences(id) ON DELETE CASCADE UNIQUE,
                tree_structure JSONB NOT NULL,        -- полное дерево в JSON формате
                parser_type VARCHAR(50) DEFAULT 'spacy',  -- какой анализатор использовался
                parser_version VARCHAR(20),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """,
            
            """
            CREATE TABLE IF NOT EXISTS public.sentence_parts (
                id SERIAL PRIMARY KEY,
                sentence_id INTEGER NOT NULL REFERENCES public.sentences(id) ON DELETE CASCADE,
                token_id INTEGER NOT NULL REFERENCES public.tokens(id) ON DELETE CASCADE,
                part_type VARCHAR(50) NOT NULL,       -- subject, predicate, object, etc.
                part_name VARCHAR(50),                 -- подлежащее, сказуемое и т.д.
                head_of_group BOOLEAN DEFAULT FALSE,   -- является ли главным в группе
                group_id INTEGER,                       -- ID синтаксической группы
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """,
            
            """
            CREATE TABLE IF NOT EXISTS public.syntax_groups (
                id SERIAL PRIMARY KEY,
                sentence_id INTEGER NOT NULL REFERENCES public.sentences(id) ON DELETE CASCADE,
                group_type VARCHAR(50) NOT NULL,       -- NP (именная), VP (глагольная), PP (предложная)
                head_token_id INTEGER REFERENCES public.tokens(id),
                start_token_index INTEGER NOT NULL,
                end_token_index INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """,
            
            """
            CREATE INDEX IF NOT EXISTS idx_syntax_relations_sentence ON public.syntax_relations(sentence_id)
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_syntax_relations_type ON public.syntax_relations(relation_type)
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_syntax_relations_head ON public.syntax_relations(head_token_id)
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_syntax_relations_dependent ON public.syntax_relations(dependent_token_id)
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_sentence_parts_sentence ON public.sentence_parts(sentence_id)
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_sentence_parts_type ON public.sentence_parts(part_type)
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_syntax_groups_sentence ON public.syntax_groups(sentence_id)
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_syntax_groups_type ON public.syntax_groups(group_type)
            """
        ]
        
        cursor = self.conn.connection.cursor()
        for query in queries:
            try:
                cursor.execute(query)
                print(f"  Таблица синтаксиса создана")
            except Exception as e:
                print(f"  Ошибка создания таблицы синтаксиса: {e}")
        self.conn.connection.commit()
        cursor.close()
        print("Таблицы для синтаксического анализа созданы")
    
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
        
    def add_syntax_relation(self, sentence_id: int, head_token_id: int, 
                        dependent_token_id: int, relation_type: str,
                        relation_name: str = None, confidence: float = 1.0) -> Optional[int]:
        """Добавление синтаксического отношения"""
        
        # Проверяем, что оба токена существуют и не совпадают
        if head_token_id == dependent_token_id:
            print(f"Предупреждение: head_token_id и dependent_token_id совпадают ({head_token_id}) - пропускаем")
            return None
        
        # Проверяем существование токенов
        cursor = self.conn.connection.cursor()
        cursor.execute("""
            SELECT id FROM public.tokens 
            WHERE id IN (%s, %s)
        """, (head_token_id, dependent_token_id))
        existing_ids = {row[0] for row in cursor.fetchall()}
        cursor.close()
        
        missing_ids = []
        if head_token_id not in existing_ids:
            missing_ids.append(str(head_token_id))
        if dependent_token_id not in existing_ids:
            missing_ids.append(str(dependent_token_id))
        
        if missing_ids:
            print(f"Предупреждение: токены с ID {', '.join(missing_ids)} не найдены в БД")
            return None
        
        # Проверяем, не существует ли уже такое отношение
        cursor = self.conn.connection.cursor()
        cursor.execute("""
            SELECT id FROM public.syntax_relations 
            WHERE sentence_id = %s AND head_token_id = %s AND dependent_token_id = %s
        """, (sentence_id, head_token_id, dependent_token_id))
        existing = cursor.fetchone()
        cursor.close()
        
        if existing:
            print(f"Отношение уже существует: {head_token_id} -> {dependent_token_id} ({relation_type})")
            return existing[0]
        
        query = """
            INSERT INTO public.syntax_relations 
            (sentence_id, head_token_id, dependent_token_id, relation_type, relation_name, confidence)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id
        """
        
        try:
            cursor = self.conn.connection.cursor()
            cursor.execute(query, (sentence_id, head_token_id, dependent_token_id, 
                                relation_type, relation_name, confidence))
            relation_id = cursor.fetchone()[0]
            self.conn.connection.commit()
            cursor.close()
            return relation_id
        except Exception as e:
            print(f"Ошибка добавления синтаксического отношения: {e}")
            self.conn.connection.rollback()
            return None
    
    def save_parse_tree(self, sentence_id: int, tree_structure: Dict, 
                       parser_type: str = 'spacy') -> bool:
        """Сохранение дерева разбора"""
        query = """
            INSERT INTO public.parse_trees (sentence_id, tree_structure, parser_type)
            VALUES (%s, %s::jsonb, %s)
            ON CONFLICT (sentence_id) 
            DO UPDATE SET
                tree_structure = EXCLUDED.tree_structure,
                parser_type = EXCLUDED.parser_type,
                created_at = CURRENT_TIMESTAMP
        """
        
        try:
            cursor = self.conn.connection.cursor()
            cursor.execute(query, (sentence_id, json.dumps(tree_structure), parser_type))
            self.conn.connection.commit()
            
            cursor.execute("""
                UPDATE public.sentences 
                SET syntax_analyzed = TRUE, syntax_analyzed_at = CURRENT_TIMESTAMP
                WHERE id = %s
            """, (sentence_id,))
            self.conn.connection.commit()
            
            cursor.close()
            return True
        except Exception as e:
            print(f"Ошибка сохранения дерева разбора: {e}")
            return False
    
    def add_sentence_part(self, sentence_id: int, token_id: int, part_type: str,
                         part_name: str = None, head_of_group: bool = False,
                         group_id: int = None) -> Optional[int]:
        """Добавление члена предложения"""
        
        # Проверяем существование токена
        cursor = self.conn.connection.cursor()
        cursor.execute("SELECT id FROM public.tokens WHERE id = %s", (token_id,))
        if not cursor.fetchone():
            print(f"Предупреждение: токен с ID {token_id} не найден в БД")
            cursor.close()
            return None
        cursor.close()
        
        query = """
            INSERT INTO public.sentence_parts 
            (sentence_id, token_id, part_type, part_name, head_of_group, group_id)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id
        """
        
        try:
            cursor = self.conn.connection.cursor()
            cursor.execute(query, (sentence_id, token_id, part_type, part_name, 
                                  head_of_group, group_id))
            part_id = cursor.fetchone()[0]
            self.conn.connection.commit()
            cursor.close()
            return part_id
        except Exception as e:
            print(f"Ошибка добавления члена предложения: {e}")
            self.conn.connection.rollback()
            return None
    
    def add_syntax_group(self, sentence_id: int, group_type: str,
                        head_token_id: int, start_index: int, 
                        end_index: int) -> Optional[int]:
        """Добавление синтаксической группы"""
        query = """
            INSERT INTO public.syntax_groups 
            (sentence_id, group_type, head_token_id, start_token_index, end_token_index)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id
        """
        
        try:
            cursor = self.conn.connection.cursor()
            cursor.execute(query, (sentence_id, group_type, head_token_id, 
                                  start_index, end_index))
            group_id = cursor.fetchone()[0]
            self.conn.connection.commit()
            cursor.close()
            return group_id
        except Exception as e:
            print(f"Ошибка добавления синтаксической группы: {e}")
            return None
    
    def get_sentence_syntax(self, sentence_id: int) -> Dict:
        """Получение всей синтаксической информации о предложении"""
        result = {
            'relations': [],
            'tree': None,
            'parts': [],
            'groups': []
        }
        
        try:
            cursor = self.conn.connection.cursor(cursor_factory=DictCursor)
            
            cursor.execute("""
                SELECT sr.*, 
                       h.token_text as head_text, d.token_text as dependent_text,
                       h.token_index as head_idx, d.token_index as dep_idx
                FROM public.syntax_relations sr
                JOIN public.tokens h ON sr.head_token_id = h.id
                JOIN public.tokens d ON sr.dependent_token_id = d.id
                WHERE sr.sentence_id = %s
                ORDER BY sr.id
            """, (sentence_id,))
            result['relations'] = [dict(row) for row in cursor.fetchall()]
            
            cursor.execute("""
                SELECT tree_structure, parser_type 
                FROM public.parse_trees 
                WHERE sentence_id = %s
            """, (sentence_id,))
            tree_row = cursor.fetchone()
            if tree_row:
                result['tree'] = {
                    'structure': tree_row['tree_structure'],
                    'parser_type': tree_row['parser_type']
                }
            
            cursor.execute("""
                SELECT sp.*, t.token_text, t.token_index
                FROM public.sentence_parts sp
                JOIN public.tokens t ON sp.token_id = t.id
                WHERE sp.sentence_id = %s
                ORDER BY t.token_index
            """, (sentence_id,))
            result['parts'] = [dict(row) for row in cursor.fetchall()]
            
            cursor.execute("""
                SELECT sg.*, t.token_text as head_text
                FROM public.syntax_groups sg
                LEFT JOIN public.tokens t ON sg.head_token_id = t.id
                WHERE sg.sentence_id = %s
                ORDER BY sg.start_token_index
            """, (sentence_id,))
            result['groups'] = [dict(row) for row in cursor.fetchall()]
            
            cursor.close()
            
        except Exception as e:
            print(f"Ошибка получения синтаксиса: {e}")
        
        return result
    
    def search_by_syntax_pattern(self, pattern: Dict, domain: str = 'animals') -> List[Dict]:
        """
        Поиск предложений по синтаксическому шаблону
        
        Args:
            pattern: словарь с параметрами поиска
            domain: предметная область
        
        Returns:
            Список найденных предложений с полями включая sentence_id
        """
        query = """
            SELECT DISTINCT s.id as sentence_id, s.sentence_text, d.title as document_title,
                h.token_text as head_word, h_t.word_form as head_form,
                dep.token_text as dependent_word, dep_t.word_form as dependent_form,
                sr.relation_type,
                hm.part_of_speech as head_pos,
                dm.part_of_speech as dep_pos
            FROM public.syntax_relations sr
            JOIN public.sentences s ON sr.sentence_id = s.id
            JOIN public.documents d ON s.document_id = d.id
            JOIN public.tokens h ON sr.head_token_id = h.id
            LEFT JOIN public.word_forms h_t ON h.word_form_id = h_t.id
            JOIN public.tokens dep ON sr.dependent_token_id = dep.id
            LEFT JOIN public.word_forms dep_t ON dep.word_form_id = dep_t.id
            LEFT JOIN public.morphology hm ON h_t.id = hm.word_form_id
            LEFT JOIN public.morphology dm ON dep_t.id = dm.word_form_id
            WHERE d.domain = %s
        """
        params = [domain]
        
        if pattern.get('relation_type'):
            query += " AND sr.relation_type = %s"
            params.append(pattern['relation_type'])
        
        if pattern.get('head_pos'):
            query += " AND hm.part_of_speech = %s"
            params.append(pattern['head_pos'])
        
        if pattern.get('dependent_pos'):
            query += " AND dm.part_of_speech = %s"
            params.append(pattern['dependent_pos'])
        
        if pattern.get('head_word'):
            query += " AND h_t.word_form = %s"
            params.append(pattern['head_word'])
        
        if pattern.get('dependent_word'):
            query += " AND dep_t.word_form = %s"
            params.append(pattern['dependent_word'])
        
        query += " LIMIT 200"
        
        try:
            cursor = self.conn.connection.cursor(cursor_factory=DictCursor)
            cursor.execute(query, params)
            rows = cursor.fetchall()
            
            results = []
            for row in rows:
                results.append({
                    'sentence_id': row['sentence_id'],  # ВАЖНО!
                    'sentence_text': row['sentence_text'],
                    'document_title': row['document_title'],
                    'head_word': row['head_word'],
                    'head_form': row['head_form'],
                    'head_pos': row['head_pos'],
                    'dependent_word': row['dependent_word'],
                    'dependent_form': row['dependent_form'],
                    'dep_pos': row['dep_pos'],
                    'relation_type': row['relation_type']
                })
            
            cursor.close()
            print(f"DEBUG: Найдено {len(results)} результатов синтаксического поиска")
            return results
            
        except Exception as e:
            print(f"Ошибка поиска по синтаксису: {e}")
            import traceback
            traceback.print_exc()
            return []
    
    def get_syntax_statistics(self, domain: str = 'animals') -> Dict:
        """Статистика по синтаксическим конструкциям"""
        stats = {}
        
        queries = {
            'relation_types': """
                SELECT sr.relation_type, COUNT(*) as count
                FROM public.syntax_relations sr
                JOIN public.sentences s ON sr.sentence_id = s.id
                JOIN public.documents d ON s.document_id = d.id
                WHERE d.domain = %s
                GROUP BY sr.relation_type
                ORDER BY count DESC
            """,
            'common_relations': """
                SELECT sr.relation_type, 
                       hm.part_of_speech as head_pos,
                       dm.part_of_speech as dep_pos,
                       COUNT(*) as count
                FROM public.syntax_relations sr
                JOIN public.sentences s ON sr.sentence_id = s.id
                JOIN public.documents d ON s.document_id = d.id
                JOIN public.tokens h ON sr.head_token_id = h.id
                JOIN public.word_forms h_t ON h.word_form_id = h_t.id
                JOIN public.morphology hm ON h_t.id = hm.word_form_id
                JOIN public.tokens dep ON sr.dependent_token_id = dep.id
                JOIN public.word_forms dep_t ON dep.word_form_id = dep_t.id
                JOIN public.morphology dm ON dep_t.id = dm.word_form_id
                WHERE d.domain = %s
                GROUP BY sr.relation_type, hm.part_of_speech, dm.part_of_speech
                ORDER BY count DESC
                LIMIT 20
            """,
            'avg_relations_per_sentence': """
                SELECT AVG(rel_count) as avg_relations
                FROM (
                    SELECT sr.sentence_id, COUNT(*) as rel_count
                    FROM public.syntax_relations sr
                    JOIN public.sentences s ON sr.sentence_id = s.id
                    JOIN public.documents d ON s.document_id = d.id
                    WHERE d.domain = %s
                    GROUP BY sr.sentence_id
                ) as sentence_relations
            """,
            'sentences_with_syntax': """
                SELECT COUNT(*) as count
                FROM public.sentences s
                JOIN public.documents d ON s.document_id = d.id
                WHERE d.domain = %s AND s.syntax_analyzed = TRUE
            """,
            'group_types': """
                SELECT sg.group_type, COUNT(*) as count
                FROM public.syntax_groups sg
                JOIN public.sentences s ON sg.sentence_id = s.id
                JOIN public.documents d ON s.document_id = d.id
                WHERE d.domain = %s
                GROUP BY sg.group_type
                ORDER BY count DESC
            """,
            'part_types': """
                SELECT sp.part_type, sp.part_name, COUNT(*) as count
                FROM public.sentence_parts sp
                JOIN public.sentences s ON sp.sentence_id = s.id
                JOIN public.documents d ON s.document_id = d.id
                WHERE d.domain = %s
                GROUP BY sp.part_type, sp.part_name
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
            print(f"Ошибка получения синтаксической статистики: {e}")
        
        return stats
    
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
                   (SELECT COUNT(*) FROM public.sentences WHERE document_id = d.id) as sentence_count,
                   (SELECT COUNT(*) FROM public.sentences WHERE document_id = d.id AND syntax_analyzed = TRUE) as syntax_analyzed_count
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
            SELECT s.sentence_text, s.id as sentence_id, d.title as document_title, 
                t.token_index, m.normal_form as lemma, t.token_text
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
                    'sentence_id': row['sentence_id'],  # ВАЖНО!
                    'document_title': row['document_title'],
                    'token_index': row['token_index'],
                    'lemma': row['lemma'],
                    'token_text': row['token_text']
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