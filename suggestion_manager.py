import json
from typing import Dict, List, Optional
from collections import defaultdict

class MorphologySuggestionManager:
    
    def __init__(self, suggestions_file: str = "morphology_suggestions.json"):
        self.suggestions_file = suggestions_file
        self.suggestions = defaultdict(list)
        self.accepted = {}
        self.rejected = defaultdict(set)
        
        self.load_suggestions()
    
    def add_suggestion(self, word: str, suggestion: Dict) -> bool:
        if not suggestion:
            return False
        
        suggestion_hash = self._hash_suggestion(suggestion)
        
        if suggestion_hash in self.rejected[word]:
            print(f"Предложение для '{word}' было ранее отклонено")
            return False
        
        for existing in self.suggestions.get(word, []):
            if existing['hash'] == suggestion_hash:
                return False
        
        self.suggestions[word].append({
            'suggestion': suggestion,
            'hash': suggestion_hash,
            'timestamp': self._current_timestamp()
        })
        
        self.save_suggestions()
        return True
    
    def get_suggestions(self, word: str) -> List[Dict]:
        return [s['suggestion'] for s in self.suggestions.get(word, [])]
    
    def accept_suggestion(self, word: str, suggestion_hash: str) -> bool:
        for suggestion in self.suggestions.get(word, []):
            if suggestion['hash'] == suggestion_hash:
                self.accepted[word] = suggestion['suggestion']
                self.remove_suggestion(word, suggestion_hash)
                self.save_suggestions()
                return True
        return False
    
    def reject_suggestion(self, word: str, suggestion_hash: str) -> bool:
        self.rejected[word].add(suggestion_hash)
        self.remove_suggestion(word, suggestion_hash)
        self.save_suggestions()
        return True
    
    def remove_suggestion(self, word: str, suggestion_hash: str) -> bool:
        if word in self.suggestions:
            self.suggestions[word] = [
                s for s in self.suggestions[word] 
                if s['hash'] != suggestion_hash
            ]
            
            if not self.suggestions[word]:
                del self.suggestions[word]
            
            return True
        return False
    
    def get_accepted(self, word: str) -> Optional[Dict]:
        return self.accepted.get(word)
    
    def has_accepted_suggestion(self, word: str) -> bool:
        return word in self.accepted
    
    def _hash_suggestion(self, suggestion: Dict) -> str:
        import hashlib
        data = json.dumps(suggestion, sort_keys=True).encode('utf-8')
        return hashlib.md5(data).hexdigest()[:8]
    
    def _current_timestamp(self) -> str:
        from datetime import datetime
        return datetime.now().isoformat()
    
    def save_suggestions(self):
        try:
            suggestions_dict = dict(self.suggestions)
            
            rejected_dict = {word: list(hashes) 
                           for word, hashes in self.rejected.items()}
            
            data = {
                'suggestions': suggestions_dict,
                'accepted': self.accepted,
                'rejected': rejected_dict,
                'metadata': {
                    'version': '1.0',
                    'saved_at': self._current_timestamp(),
                    'total_suggestions': sum(len(s) for s in self.suggestions.values()),
                    'total_accepted': len(self.accepted),
                    'total_rejected': sum(len(h) for h in self.rejected.values())
                }
            }
            
            with open(self.suggestions_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
                
        except Exception as e:
            print(f"Ошибка сохранения предложений: {e}")
    
    def load_suggestions(self):
        try:
            with open(self.suggestions_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                
                self.suggestions = defaultdict(list, data.get('suggestions', {}))
                self.accepted = data.get('accepted', {})
                
                rejected_data = data.get('rejected', {})
                self.rejected = defaultdict(set)
                for word, hashes in rejected_data.items():
                    self.rejected[word] = set(hashes)
                    
        except FileNotFoundError:
            print(f"Файл предложений не найден: {self.suggestions_file}")
            print("Создаётся новый файл предложений")
        except json.JSONDecodeError as e:
            print(f"Ошибка чтения файла предложений (возможно, файл повреждён): {e}")
            print("Создаётся новый файл предложений")
        except Exception as e:
            print(f"Ошибка загрузки предложений: {e}")
    
    def clear_all(self):
        self.suggestions.clear()
        self.accepted.clear()
        self.rejected.clear()
        self.save_suggestions()
    
    def get_stats(self) -> Dict:
        return {
            'total_words_with_suggestions': len(self.suggestions),
            'total_suggestions': sum(len(s) for s in self.suggestions.values()),
            'total_accepted': len(self.accepted),
            'total_rejected': sum(len(h) for h in self.rejected.values()),
            'most_suggested_words': sorted(
                [(word, len(suggestions)) for word, suggestions in self.suggestions.items()],
                key=lambda x: x[1],
                reverse=True
            )[:10]
        }
    
    def print_stats(self):
        stats = self.get_stats()
        print("\n=== СТАТИСТИКА ПРЕДЛОЖЕНИЙ ===")
        print(f"Слов с предложениями: {stats['total_words_with_suggestions']}")
        print(f"Всего предложений: {stats['total_suggestions']}")
        print(f"Принято: {stats['total_accepted']}")
        print(f"Отклонено: {stats['total_rejected']}")
        print("\nТоп слов по количеству предложений:")
        for word, count in stats['most_suggested_words']:
            print(f"  {word}: {count} предложений")
        print("=" * 30)

_suggestion_manager_instance = None

def get_suggestion_manager() -> MorphologySuggestionManager:
    global _suggestion_manager_instance
    if _suggestion_manager_instance is None:
        _suggestion_manager_instance = MorphologySuggestionManager()
    return _suggestion_manager_instance