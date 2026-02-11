import pymorphy3
from typing import Dict, Optional

class MorphologyAnalyzer:
    def __init__(self):
        self.morph = pymorphy3.MorphAnalyzer()

        self.pos_mapping = {
            'NOUN': 'существительное',
            'ADJF': 'прилагательное',
            'ADJS': 'прилагательное (краткое)',
            'COMP': 'компаратив',
            'VERB': 'глагол',
            'INFN': 'глагол (инфинитив)',
            'PRTF': 'причастие',
            'PRTS': 'причастие (краткое)',
            'GRND': 'деепричастие',
            'NUMR': 'числительное',
            'ADVB': 'наречие',
            'NPRO': 'местоимение',
            'PRED': 'предикатив',
            'PREP': 'предлог',
            'CONJ': 'союз',
            'PRCL': 'частица',
            'INTJ': 'междометие'
        }
        
        self.gender_mapping = {
            'masc': 'мужской',
            'femn': 'женский',
            'neut': 'средний',
            None: ''
        }
        
        self.number_mapping = {
            'sing': 'единственное',
            'plur': 'множественное',
            None: ''
        }
        
        self.case_mapping = {
            'nomn': 'именительный',
            'gent': 'родительный',
            'datv': 'дательный',
            'accs': 'винительный',
            'ablt': 'творительный',
            'loct': 'предложный',
            'voct': 'звательный',
            None: ''
        }
    
    def analyze_word(self, word: str) -> Dict[str, Optional[str]]:
        if not word or len(word.strip()) < 2:
            return self._empty_result()
        
        word = word.strip().lower()
        parsed = self.morph.parse(word)
        
        if not parsed:
            return self._empty_result()
        
        best_parse = parsed[0]
        tags = best_parse.tag
        part_of_speech = self._get_part_of_speech(tags)
        gender = self._get_gender(tags)
        number = self._get_number(tags)
        case_form = self._get_case(tags)
        normal_form = best_parse.normal_form
        confidence = best_parse.score
        
        return {
            'part_of_speech': part_of_speech,
            'gender': gender,
            'number': number,
            'case_form': case_form,
            'normal_form': normal_form,
            'confidence': confidence,
            'tag': str(tags),
            'parsed_word': best_parse.word
        }
    
    def _get_part_of_speech(self, tags) -> Optional[str]:
        pos = tags.POS
        return self.pos_mapping.get(pos, '')
    
    def _get_gender(self, tags) -> Optional[str]:
        gender = tags.gender
        return self.gender_mapping.get(gender, '')
    
    def _get_number(self, tags) -> Optional[str]:
        number = tags.number
        return self.number_mapping.get(number, '')
    
    def _get_case(self, tags) -> Optional[str]:
        case = tags.case
        return self.case_mapping.get(case, '')
    
    def _empty_result(self) -> Dict[str, Optional[str]]:
        return {
            'part_of_speech': None,
            'gender': None,
            'number': None,
            'case_form': None,
            'normal_form': None,
            'confidence': 0.0,
            'tag': None,
            'parsed_word': None
        }
    
    def get_all_parses(self, word: str, limit: int = 3) -> list:
        if not word or len(word.strip()) < 2:
            return []
        
        word = word.strip().lower()
        parsed = self.morph.parse(word)[:limit]
        
        results = []
        for parse in parsed:
            tags = parse.tag
            results.append({
                'part_of_speech': self._get_part_of_speech(tags),
                'gender': self._get_gender(tags),
                'number': self._get_number(tags),
                'case_form': self._get_case(tags),
                'normal_form': parse.normal_form,
                'confidence': parse.score,
                'tag': str(tags)
            })
        
        return results

_analyzer_instance = None

def get_morphology_analyzer() -> MorphologyAnalyzer:
    global _analyzer_instance
    if _analyzer_instance is None:
        _analyzer_instance = MorphologyAnalyzer()
    return _analyzer_instance