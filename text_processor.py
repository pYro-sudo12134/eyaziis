import re
from abc import ABC, abstractmethod
from striprtf.striprtf import rtf_to_text
import nltk
from nltk.tokenize import word_tokenize
from collections import Counter
from typing import List, Dict
import warnings
import PyPDF2
import subprocess
import os
from docx import Document
warnings.filterwarnings('ignore')
from morphology_analyzer import get_morphology_analyzer

class FileReaderStrategy(ABC):
    @abstractmethod
    def read(self, file_path):
        pass

class TXTReaderStrategy(FileReaderStrategy):
    def read(self, file_path):
        try:
            encodings = ['utf-8', 'cp1251', 'windows-1251', 'koi8-r', 'iso-8859-5']
            
            for encoding in encodings:
                try:
                    with open(file_path, 'r', encoding=encoding) as f:
                        return f.read()
                except UnicodeDecodeError:
                    continue
            
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                return f.read()
                
        except Exception as e:
            print(f"Ошибка чтения TXT файла {file_path}: {e}")
            return ""

class RTFReaderStrategy(FileReaderStrategy):
    def read(self, file_path):
        try:
            with open(file_path, 'rb') as f:
                rtf_bytes = f.read()
            
            encodings = ['utf-8', 'cp1251', 'windows-1251', 'koi8-r']
            
            for encoding in encodings:
                try:
                    rtf_text = rtf_bytes.decode(encoding)
                    plain_text = rtf_to_text(rtf_text)
                    return plain_text
                except (UnicodeDecodeError, Exception):
                    continue
            
            rtf_text = rtf_bytes.decode('utf-8', errors='ignore')
            return rtf_to_text(rtf_text)
            
        except Exception as e:
            print(f"Ошибка чтения RTF файла {file_path}: {e}")
            return ""

class PDFReaderStrategy(FileReaderStrategy):
    def read(self, file_path):
        if PyPDF2 is None:
            return "[PDF поддержка не установлена]"
        
        try:
            text = []
            with open(file_path, 'rb') as f:
                pdf_reader = PyPDF2.PdfReader(f)
                for page in pdf_reader.pages:
                    page_text = page.extract_text()
                    if page_text:
                        text.append(page_text)
            return '\n'.join(text)
        except Exception as e:
            print(f"Ошибка чтения PDF: {e}")
            return ""

class DOCXReaderStrategy(FileReaderStrategy):
    def read(self, file_path):
        if Document is None:
            return "[DOCX поддержка не установлена]"
        
        try:
            doc = Document(file_path)
            text = [paragraph.text for paragraph in doc.paragraphs]
            return '\n'.join(text)
        except Exception as e:
            print(f"Ошибка чтения DOCX: {e}")
            return ""

class DOCReaderStrategy(FileReaderStrategy):
    def read(self, file_path):
        try:
            result = subprocess.run(
                ['antiword', file_path], 
                capture_output=True, 
                text=True
            )
            if result.returncode == 0:
                return result.stdout
            else:
                with open(file_path, 'rb') as f:
                    content = f.read()
                    text = content.decode('utf-8', errors='ignore')
                    text = ''.join(c for c in text if c.isprintable() or c in '\n\r\t')
                    return text
        except Exception as e:
            print(f"Ошибка чтения DOC: {e}")
            return ""

class LanguageProcessorStrategy(ABC):
    @abstractmethod
    def preprocess(self, text):
        pass
    
    @abstractmethod
    def tokenize(self, text):
        pass

class RussianLanguageProcessor(LanguageProcessorStrategy):
    def __init__(self):
        self._init_nltk()
    
    def _init_nltk(self):
        try:
            nltk.data.find('tokenizers/punkt')
            nltk.data.find('tokenizers/punkt_tab')
        except LookupError:
            print("Скачивание данных NLTK для русского языка...")
            try:
                nltk.download('punkt', quiet=True)
                nltk.download('punkt_tab', quiet=True)
                print("Данные NLTK успешно скачаны")
            except Exception as e:
                print(f"Ошибка скачивания NLTK: {e}")
    
    def preprocess(self, text):
        if not text:
            return ""
        
        text = text.lower()
        text = re.sub(r'[^а-яё\s-]', ' ', text)
        text = re.sub(r'\s+', ' ', text).strip()
        
        return text
    
    def tokenize(self, text):
        if not text:
            return []
        
        try:
            return word_tokenize(text, language='russian')
        except Exception:
            return [word for word in text.split() if word.strip()]

class TextProcessor:
    def __init__(self, auto_analyze: bool = True, confidence_threshold: float = 0.3):
        self.word_counter = Counter()
        self.reader_strategy = None
        self.language_processor = RussianLanguageProcessor()
        
        self.auto_analyze = auto_analyze
        self.confidence_threshold = confidence_threshold
        
        self.morph_cache = {}
        self._morph_analyzer = None
    
    @property
    def morph_analyzer(self):
        if self._morph_analyzer is None and self.auto_analyze:
            try:
                self._morph_analyzer = get_morphology_analyzer()
                print("Морфологический анализатор инициализирован")
            except Exception as e:
                print(f"Ошибка инициализации морфологического анализатора: {e}")
                self.auto_analyze = False
        return self._morph_analyzer
    
    def set_reader_strategy(self, strategy: FileReaderStrategy):
        self.reader_strategy = strategy
    
    def set_language_processor(self, processor: LanguageProcessorStrategy):
        self.language_processor = processor
    
    def _get_reader_strategy(self, file_path):
        ext = file_path.lower()
        if ext.endswith('.txt'):
            return TXTReaderStrategy()
        elif ext.endswith('.rtf'):
            return RTFReaderStrategy()
        elif ext.endswith('.pdf'):
            return PDFReaderStrategy()
        elif ext.endswith('.docx'):
            return DOCXReaderStrategy()
        elif ext.endswith('.doc'):
            return DOCReaderStrategy()
        else:
            raise ValueError(f"Неподдерживаемый формат: {file_path}")
    
    def analyze_word_morphology(self, word: str) -> Dict:
        if not self.auto_analyze or not self.morph_analyzer:
            return {}
        
        word_key = word.lower()
        if word_key in self.morph_cache:
            return self.morph_cache[word_key]
        
        try:
            result = self.morph_analyzer.analyze_word(word)
            self.morph_cache[word_key] = result
            return result
        except Exception as e:
            print(f"Ошибка анализа слова '{word}': {e}")
            return {}
    
    def batch_analyze_words(self, words: List[str]) -> Dict[str, Dict]:
        if not self.auto_analyze:
            return {}
        
        results = {}
        for word in words:
            if word not in results:
                results[word] = self.analyze_word_morphology(word)
        
        return results
    
    def process_file(self, file_path, return_morphology: bool = False):
        print(f"Обработка файла: {file_path}")
        
        if not file_path:
            return Counter() if not return_morphology else (Counter(), {})
        
        try:
            strategy = self._get_reader_strategy(file_path)
            text = strategy.read(file_path)
            
            if not text or text.strip() == "":
                print("Файл пуст или содержит только пробелы")
                return Counter() if not return_morphology else (Counter(), {})
            
            cleaned_text = self.language_processor.preprocess(text)
            print(f"Текст очищен, длина: {len(cleaned_text)} символов")
            
            tokens = self.language_processor.tokenize(cleaned_text)
            print(f"Получено токенов: {len(tokens)}")
            
            valid_tokens = [token for token in tokens if len(token) > 1]
            self.word_counter = Counter(valid_tokens)
            
            print(f"Уникальных словоформ: {len(self.word_counter)}")
            
            morphology_results = {}
            if return_morphology and self.auto_analyze:
                print("Выполнение морфологического анализа...")
                
                top_words = [word for word, _ in self.word_counter.most_common(100)]
                morphology_results = self.batch_analyze_words(top_words)
                
                high_conf = sum(1 for r in morphology_results.values() 
                              if r.get('confidence', 0) > self.confidence_threshold)
                print(f"Морфологический анализ выполнен: {high_conf}/{len(morphology_results)} "
                      f"слов с высокой достоверностью (>{self.confidence_threshold})")
            
            if return_morphology:
                return self.word_counter, morphology_results
            else:
                return self.word_counter
            
        except ValueError as e:
            print(f"Ошибка: {e}")
            return Counter() if not return_morphology else (Counter(), {})
        except Exception as e:
            print(f"Ошибка обработки файла: {e}")
            return Counter() if not return_morphology else (Counter(), {})
    
    def get_top_words(self, n=20):
        return self.word_counter.most_common(n)
    
    def get_suggested_morphology(self, word: str) -> Dict:
        if not self.auto_analyze or not self.morph_analyzer:
            return {}
        
        result = self.analyze_word_morphology(word)
        
        if result.get('confidence', 0) < self.confidence_threshold:
            return {}
        
        suggestion = {
            'part_of_speech': result.get('part_of_speech'),
            'gender': result.get('gender'),
            'number': result.get('number'),
            'case_form': result.get('case_form'),
            'normal_form': result.get('normal_form'),
            'confidence': result.get('confidence'),
            'tag': result.get('tag')
        }
        
        suggestion = {k: v for k, v in suggestion.items() 
                    if v is not None and v != ''}
        
        return suggestion if suggestion else {}
    
    def clear_cache(self):
        self.morph_cache.clear()