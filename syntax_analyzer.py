# syntax_analyzer.py

import spacy
from typing import List, Dict, Optional, Tuple, Any
import json
from datetime import datetime

class SyntaxAnalyzer:
    """
    Синтаксический анализатор для русского языка на основе spaCy
    """
    
    # Маппинг типов зависимостей на русские названия
    DEP_MAPPING = {
        'nsubj': 'подлежащее',
        'nsubj:pass': 'подлежащее (пассив)',
        'obj': 'дополнение',
        'iobj': 'косвенное дополнение',
        'obl': 'обстоятельство',
        'nmod': 'именное определение',
        'amod': 'согласованное определение',
        'advmod': 'обстоятельство (наречие)',
        'advcl': 'придаточное обстоятельственное',
        'aux': 'вспомогательный глагол',
        'aux:pass': 'вспомогательный глагол (пассив)',
        'cop': 'связка',
        'mark': 'маркер придаточного',
        'cc': 'сочинительный союз',
        'conj': 'сочинительная связь',
        'case': 'предлог',
        'punct': 'пунктуация',
        'root': 'корень предложения',
        'parataxis': 'паратаксис',
        'appos': 'приложение',
        'nummod': 'числительное',
        'xcomp': 'дополнение (инфинитив)',
        'ccomp': 'придаточное дополнительное',
        'acl': 'определительное придаточное',
        'det': 'определитель',
        'flat': 'часть составной единицы',
        'fixed': 'фиксированное выражение',
        'compound': 'сложное слово'
    }
    
    # Маппинг частей речи на русские названия
    POS_MAPPING = {
        'NOUN': 'существительное',
        'ADJ': 'прилагательное',
        'ADP': 'предлог',
        'ADV': 'наречие',
        'AUX': 'вспомогательный глагол',
        'CCONJ': 'сочинительный союз',
        'DET': 'определитель',
        'INTJ': 'междометие',
        'NUM': 'числительное',
        'PART': 'частица',
        'PRON': 'местоимение',
        'PROPN': 'имя собственное',
        'PUNCT': 'пунктуация',
        'SCONJ': 'подчинительный союз',
        'SYM': 'символ',
        'VERB': 'глагол',
        'X': 'другое'
    }
    
    def __init__(self, model_name: str = 'ru_core_news_sm'):
        """
        Инициализация синтаксического анализатора
        
        Args:
            model_name: название модели spaCy для русского языка
        """
        print(f"Загрузка модели spaCy: {model_name}")
        try:
            self.nlp = spacy.load(model_name)
            print("Модель успешно загружена")
        except OSError:
            print(f"Модель {model_name} не найдена. Скачивание...")
            spacy.cli.download(model_name)
            self.nlp = spacy.load(model_name)
            print("Модель загружена")
        
        # Кэш для результатов анализа
        self.analysis_cache = {}
    
    def parse_sentence(self, sentence_text: str, sentence_id: int = None) -> Dict:
        """
        Полный синтаксический разбор предложения
        
        Args:
            sentence_text: текст предложения
            sentence_id: ID предложения в БД (для кэширования)
        
        Returns:
            Dict с результатами разбора
        """
        # Проверяем кэш
        cache_key = sentence_text.strip()
        if cache_key in self.analysis_cache:
            return self.analysis_cache[cache_key]
        
        # Обрабатываем предложение
        doc = self.nlp(sentence_text)
        
        # Основные результаты
        result = {
            'tokens': [],
            'relations': [],
            'tree': {
                'nodes': [],
                'edges': []
            },
            'sentence_parts': {
                'subject': [],
                'predicate': [],
                'object': [],
                'adverbial': [],
                'attribute': []
            },
            'groups': {
                'noun_phrases': [],
                'verb_phrases': [],
                'prepositional_phrases': []
            },
            'statistics': {
                'token_count': len(doc),
                'relation_count': 0,
                'root': None,
                'depth': 0
            }
        }
        
        # Собираем токены
        for token in doc:
            token_info = {
                'id': token.i,
                'text': token.text,
                'lemma': token.lemma_,
                'pos': token.pos_,
                'pos_rus': self.POS_MAPPING.get(token.pos_, token.pos_),
                'tag': token.tag_,
                'morph': str(token.morph) if token.morph else '',
                'is_punct': token.is_punct,
                'is_stop': token.is_stop,
                'is_alpha': token.is_alpha,
                'is_digit': token.is_digit,
                'shape': token.shape_
            }
            result['tokens'].append(token_info)
            result['tree']['nodes'].append({
                'id': token.i,
                'label': token.text,
                'pos': token.pos_,
                'pos_rus': self.POS_MAPPING.get(token.pos_, token.pos_)
            })
        
        # Собираем синтаксические отношения
        for token in doc:
            if token.dep_ != 'punct':  # Пропускаем пунктуацию для отношений
                relation = {
                    'head_id': token.head.i,
                    'head_text': token.head.text,
                    'dependent_id': token.i,
                    'dependent_text': token.text,
                    'relation_type': token.dep_,
                    'relation_name': self.DEP_MAPPING.get(token.dep_, token.dep_),
                    'confidence': 1.0
                }
                result['relations'].append(relation)
                
                # Добавляем ребро в дерево
                result['tree']['edges'].append({
                    'from': token.head.i,
                    'to': token.i,
                    'label': token.dep_,
                    'label_rus': self.DEP_MAPPING.get(token.dep_, token.dep_)
                })
                
                # Определяем члены предложения
                self._classify_sentence_part(token, relation, result['sentence_parts'])
        
        # Находим корень предложения
        for token in doc:
            if token.dep_ == 'ROOT' or token.head == token:
                result['statistics']['root'] = {
                    'id': token.i,
                    'text': token.text,
                    'pos': token.pos_
                }
                break
        
        result['statistics']['relation_count'] = len(result['relations'])
        
        # Выделяем синтаксические группы (без noun_chunks)
        result['groups'] = self._extract_phrases_simple(doc)
        
        # Вычисляем глубину дерева
        result['statistics']['depth'] = self._calculate_tree_depth(result['relations'])
        
        # Кэшируем результат
        if sentence_id:
            self.analysis_cache[cache_key] = result
        
        return result
    
    def _classify_sentence_part(self, token, relation: Dict, parts: Dict):
        """
        Классификация члена предложения на основе типа зависимости
        """
        dep = relation['relation_type']
        
        if dep.startswith('nsubj'):
            parts['subject'].append({
                'token_id': token.i,
                'text': token.text,
                'head_id': relation['head_id'],
                'relation_type': dep
            })
        elif dep in ('obj', 'iobj', 'obl'):
            parts['object'].append({
                'token_id': token.i,
                'text': token.text,
                'head_id': relation['head_id'],
                'relation_type': dep
            })
        elif dep in ('amod', 'nmod', 'nummod', 'appos', 'acl'):
            parts['attribute'].append({
                'token_id': token.i,
                'text': token.text,
                'head_id': relation['head_id'],
                'relation_type': dep
            })
        elif dep in ('advmod', 'advcl', 'obl'):
            parts['adverbial'].append({
                'token_id': token.i,
                'text': token.text,
                'head_id': relation['head_id'],
                'relation_type': dep
            })
        elif dep in ('ROOT', 'cop', 'aux'):
            parts['predicate'].append({
                'token_id': token.i,
                'text': token.text,
                'head_id': relation['head_id'],
                'relation_type': dep
            })
    
    def _extract_phrases_simple(self, doc) -> Dict:
        """
        Выделение синтаксических групп (без использования noun_chunks)
        """
        groups = {
            'noun_phrases': [],
            'verb_phrases': [],
            'prepositional_phrases': []
        }
        
        # Ищем существительные с их определениями
        for token in doc:
            if token.pos_ == 'NOUN':
                # Собираем зависимые от существительного слова
                dependents = [child for child in token.children]
                adjectives = [child for child in dependents if child.pos_ == 'ADJ']
                
                if adjectives:
                    groups['noun_phrases'].append({
                        'head_id': token.i,
                        'head_text': token.text,
                        'dependents': [{'id': adj.i, 'text': adj.text} for adj in adjectives],
                        'text': ' '.join([adj.text for adj in adjectives] + [token.text])
                    })
        
        # Выделяем глагольные группы
        for token in doc:
            if token.pos_ == 'VERB':
                # Собираем зависимые от глагола слова
                dependents = [child for child in token.children]
                if dependents:
                    groups['verb_phrases'].append({
                        'head_id': token.i,
                        'head_text': token.text,
                        'dependents': [{'id': dep.i, 'text': dep.text} for dep in dependents],
                        'text': token.text + ' ' + ' '.join([dep.text for dep in dependents if dep.i > token.i][:3])
                    })
        
        # Выделяем предложные группы
        for token in doc:
            if token.pos_ == 'ADP':
                # Находим существительное, связанное с предлогом
                for child in token.children:
                    if child.pos_ in ('NOUN', 'PROPN'):
                        groups['prepositional_phrases'].append({
                            'preposition': token.text,
                            'head_id': child.i,
                            'head_text': child.text,
                            'text': f"{token.text} {child.text}"
                        })
                        break
        
        return groups
    
    def _calculate_tree_depth(self, relations: List[Dict]) -> int:
        """
        Вычисление максимальной глубины дерева зависимостей
        """
        if not relations:
            return 0
        
        # Строим граф
        graph = {}
        for rel in relations:
            head = rel['head_id']
            dep = rel['dependent_id']
            if head not in graph:
                graph[head] = []
            graph[head].append(dep)
        
        # Находим корни (узлы, которые ни от кого не зависят)
        all_deps = set(rel['dependent_id'] for rel in relations)
        all_heads = set(rel['head_id'] for rel in relations)
        roots = all_heads - all_deps
        
        if not roots:
            return 0
        
        # BFS для поиска максимальной глубины
        max_depth = 0
        for root in roots:
            depth = self._bfs_depth(graph, root)
            max_depth = max(max_depth, depth)
        
        return max_depth
    
    def _bfs_depth(self, graph: Dict, start: int) -> int:
        """BFS для вычисления глубины от стартового узла"""
        visited = set()
        queue = [(start, 0)]
        max_depth = 0
        
        while queue:
            node, depth = queue.pop(0)
            if node in visited:
                continue
            visited.add(node)
            max_depth = max(max_depth, depth)
            
            for child in graph.get(node, []):
                if child not in visited:
                    queue.append((child, depth + 1))
        
        return max_depth
    
    def to_conllu(self, parse_result: Dict) -> str:
        """
        Экспорт в формат CONLL-U
        """
        lines = []
        lines.append("# sent_id = 1")
        lines.append(f"# text = {parse_result.get('sentence_text', '')}")
        
        # Создаем словарь отношений для быстрого доступа
        rel_dict = {}
        for rel in parse_result['relations']:
            rel_dict[rel['dependent_id']] = rel
        
        for token in parse_result['tokens']:
            token_id = token['id'] + 1
            
            # Находим голову
            if token_id - 1 in rel_dict:
                head = rel_dict[token_id - 1]['head_id'] + 1
                deprel = rel_dict[token_id - 1]['relation_type']
            else:
                head = 0
                deprel = 'root'
            
            line = f"{token_id}\t{token['text']}\t{token['lemma']}\t{token['pos']}\t{token['tag']}\t_\t{head}\t{deprel}\t_\t_"
            lines.append(line)
        
        return '\n'.join(lines)


# Глобальный экземпляр для использования в приложении
_syntax_analyzer_instance = None

def get_syntax_analyzer() -> SyntaxAnalyzer:
    """Получение глобального экземпляра синтаксического анализатора"""
    global _syntax_analyzer_instance
    if _syntax_analyzer_instance is None:
        _syntax_analyzer_instance = SyntaxAnalyzer()
    return _syntax_analyzer_instance