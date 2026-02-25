#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Скрипт для инициализации корпуса и загрузки демонстрационных текстов
"""

import os
import sys
import psycopg2
from psycopg2.extras import DictCursor
from database import PostgreSQLConnection
from corpus_manager import CorpusManager

# Демонстрационные тексты о животных
DEMO_TEXTS = [
    {
        'title': 'Бурый медведь',
        'author': 'В.Н. Большаков',
        'year': 2015,
        'genre': 'научно-популярный',
        'source': 'Энциклопедия животных России',
        'content': '''
        Бурый медведь — крупное хищное млекопитающее семейства медвежьих. Длина тела достигает 2-2,5 метра,
        масса до 400-500 килограммов. Бурые медведи обитают в лесах Евразии и Северной Америки.
        Это всеядные животные, питающиеся как растительной, так и животной пищей. В рацион медведя
        входят ягоды, орехи, коренья, насекомые, рыба и мелкие млекопитающие. Зимой медведи впадают
        в спячку в берлоге. Медведица приносит 1-3 медвежат, которые остаются с матерью до 2-3 лет.
        Бурый медведь — один из самых крупных наземных хищников. Он хорошо плавает и лазает по деревьям.
        В России бурый медведь широко распространён в лесной зоне. Медведь является символом силы и мощи
        во многих культурах. Охота на медведя строго регулируется, вид включён в Красные книги некоторых
        регионов.
        '''
    },
    {
        'title': 'Амурский тигр',
        'author': 'Д.Г. Пикунов',
        'year': 2018,
        'genre': 'научный',
        'source': 'Зоологический журнал',
        'content': '''
        Амурский тигр — один из самых редких подвидов тигра, сохранившийся на Дальнем Востоке России.
        Это крупнейший представитель кошачьих: вес самца может достигать 300 килограммов, длина тела
        до 3 метров. Амурские тигры обитают в кедрово-широколиственных лесах Приморского и Хабаровского
        краёв. Основу питания составляют копытные: кабаны, изюбри, пятнистые олени. Тигр — одиночное
        территориальное животное. Охотничий участок самца занимает 600-800 квадратных километров.
        Тигрица приносит 2-4 тигрёнка. Молодые тигры остаются с матерью до 2 лет. Амурский тигр
        занесён в Красную книгу России и Международного союза охраны природы. Благодаря природоохранным
        мерам численность подвида увеличилась и сейчас составляет около 600 особей.
        '''
    },
    {
        'title': 'Обыкновенная лисица',
        'author': 'И.И. Барабаш-Никифоров',
        'year': 2016,
        'genre': 'научно-популярный',
        'source': 'Жизнь животных',
        'content': '''
        Обыкновенная лисица — хищное млекопитающее семейства псовых, наиболее распространённый вид
        лисиц. Длина тела 60-90 сантиметров, масса до 10 килограммов. Лисица отличается пушистым хвостом,
        длина которого достигает 40-60 сантиметров. Окраска варьирует от рыжей до серебристо-чёрной.
        Лисицы обитают в различных ландшафтах: в тундре, лесах, степях, пустынях. Они селятся в норах,
        которые роют сами или занимают жилища других животных. Лисица всеядна, но основу питания составляют
        грызуны — мыши, полёвки. Она также охотится на зайцев, птиц, поедает насекомых и плоды.
        Лисица — герой многих сказок и легенд, символ хитрости и ловкости. Охота на лисицу ведётся
        ради ценного меха. В городах лисицы могут питаться отбросами и привыкают к человеку.
        '''
    }
]

def drop_all_tables(conn):
    """Полное удаление всех таблиц"""
    try:
        cursor = conn.connection.cursor()
        
        # Отключаем проверку внешних ключей
        cursor.execute("SET session_replication_role = 'replica';")
        
        # Удаляем таблицы в правильном порядке (сначала зависимые)
        tables = ['concordance', 'tokens', 'sentences', 'morphology', 'word_forms', 'documents']
        
        for table in tables:
            try:
                cursor.execute(f"DROP TABLE IF EXISTS public.{table} CASCADE;")
                print(f"  ✓ Таблица {table} удалена")
            except Exception as e:
                print(f"  ✗ Ошибка при удалении {table}: {e}")
        
        # Включаем обратно проверку внешних ключей
        cursor.execute("SET session_replication_role = 'origin';")
        
        conn.connection.commit()
        cursor.close()
        print("Все таблицы успешно удалены")
        return True
        
    except Exception as e:
        print(f"Ошибка при удалении таблиц: {e}")
        try:
            conn.connection.rollback()
        except:
            pass
        return False

def init_corpus():
    """Инициализация корпуса демонстрационными текстами"""
    print("Инициализация корпуса текстов о животных...")
    
    # Подключение к БД
    db_connection = PostgreSQLConnection()
    
    try:
        # Устанавливаем соединение
        print("Подключение к PostgreSQL...")
        db_connection.connect()
        print("Подключение установлено!")
        
        # Удаляем все существующие таблицы
        print("\nУдаление старых таблиц...")
        drop_all_tables(db_connection)
        
        # Создаем менеджер корпуса (таблицы создадутся заново с правильной структурой)
        print("\nСоздание таблиц с правильной структурой...")
        corpus_manager = CorpusManager(db_connection)
        
        # Создание временной папки для текстов
        os.makedirs('corpus/animals', exist_ok=True)
        
        for i, text_data in enumerate(DEMO_TEXTS):
            print(f"\nОбработка текста {i+1}: {text_data['title']}")
            
            # Создание временного файла
            filename = f"demo_text_{i+1}.txt"
            filepath = os.path.join('corpus/animals', filename)
            
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(text_data['content'])
            
            # Метаданные
            metadata = {
                'title': text_data['title'],
                'author': text_data['author'],
                'year': text_data['year'],
                'genre': text_data['genre'],
                'source': text_data['source']
            }
            
            # Обработка документа
            results = corpus_manager.process_document(filepath, metadata)
            
            if results['success']:
                print(f"  ✓ Успешно обработан")
                print(f"    Предложений: {results['sentences_count']}")
                print(f"    Токенов: {results['tokens_count']}")
            else:
                print(f"  ✗ Ошибка: {', '.join(results['errors'])}")
        
        print("\n" + "="*50)
        print("Инициализация корпуса завершена")
        
        # Вывод статистики
        stats = corpus_manager.get_statistics()
        print(f"\nСтатистика корпуса:")
        print(f"  Документов: {stats['documents']}")
        print(f"  Предложений: {stats['sentences']}")
        print(f"  Слов: {stats['tokens']}")
        print(f"  Уникальных слов: {stats['unique_words']}")
        
        # Вывод статистики по частям речи
        if stats.get('morphology') and stats['morphology'].get('part_of_speech'):
            print(f"\nРаспределение по частям речи:")
            for pos, count in stats['morphology']['part_of_speech'][:10]:
                print(f"  {pos}: {count}")
        
    except Exception as e:
        print(f"Критическая ошибка: {e}")
        import traceback
        traceback.print_exc()
        
    finally:
        if db_connection.connected:
            db_connection.close()

def check_morphology(db_connection):
    """Проверка наличия лемм в базе"""
    cursor = db_connection.connection.cursor(cursor_factory=DictCursor)
    
    # Проверим несколько случайных словоформ
    cursor.execute("""
        SELECT wf.word_form, m.normal_form, m.confidence 
        FROM public.word_forms wf
        LEFT JOIN public.morphology m ON wf.id = m.word_form_id
        WHERE m.normal_form IS NOT NULL
        LIMIT 10
    """)
    
    results = cursor.fetchall()
    print("\n=== ПРОВЕРКА ЛЕММ В БАЗЕ ===")
    if results:
        for row in results:
            print(f"Словоформа: '{row['word_form']}' -> Лемма: '{row['normal_form']}' (достоверность: {row['confidence']})")
    else:
        print("Леммы не найдены!")
    
    # Проверим, есть ли вообще данные в morphology
    cursor.execute("SELECT COUNT(*) FROM public.morphology")
    count = cursor.fetchone()[0]
    print(f"Всего записей в morphology: {count}")
    
    cursor.close()

# Вызовите эту функцию в init_corpus.py после загрузки всех текстов
# Например, перед выводом статистики:

if __name__ == "__main__":
    init_corpus()
    # После init_corpus() добавьте:
    db_connection = PostgreSQLConnection()
    db_connection.connect()
    check_morphology(db_connection)
    db_connection.close()