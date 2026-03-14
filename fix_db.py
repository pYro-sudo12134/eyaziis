#!/usr/bin/env python3
# fix_database.py

import psycopg2
from psycopg2.extras import DictCursor

def fix_database():
    """Исправление структуры базы данных - добавление недостающих полей"""
    
    # Параметры подключения
    conn = psycopg2.connect(
        host='localhost',
        dbname='postgres',
        user='postgres',
        password='postgres',
        port=5432
    )
    
    cursor = conn.cursor()
    
    print("="*60)
    print("ИСПРАВЛЕНИЕ СТРУКТУРЫ БАЗЫ ДАННЫХ")
    print("="*60)
    
    # 1. Добавляем поля в таблицу sentences
    try:
        cursor.execute("""
            ALTER TABLE public.sentences 
            ADD COLUMN IF NOT EXISTS syntax_analyzed BOOLEAN DEFAULT FALSE,
            ADD COLUMN IF NOT EXISTS syntax_analyzed_at TIMESTAMP
        """)
        print("✅ Поля syntax_analyzed и syntax_analyzed_at добавлены в таблицу sentences")
    except Exception as e:
        print(f"❌ Ошибка при добавлении полей: {e}")
    
    # 2. Проверяем создание таблиц синтаксиса
    syntax_tables = [
        'syntax_relations',
        'parse_trees', 
        'sentence_parts',
        'syntax_groups'
    ]
    
    for table in syntax_tables:
        try:
            # Проверяем, существует ли таблица
            cursor.execute("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_schema = 'public' 
                    AND table_name = %s
                )
            """, (table,))
            exists = cursor.fetchone()[0]
            
            if exists:
                print(f"✅ Таблица {table} уже существует")
            else:
                print(f"⚠️ Таблица {table} не найдена, будет создана при следующем запуске")
                
        except Exception as e:
            print(f"❌ Ошибка при проверке таблицы {table}: {e}")
    
    # 3. Проверяем, что поля действительно добавились
    cursor.execute("""
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_name = 'sentences' 
        AND column_name IN ('syntax_analyzed', 'syntax_analyzed_at')
    """)
    columns = cursor.fetchall()
    
    if len(columns) == 2:
        print("\n✅ Все поля успешно добавлены!")
    else:
        print("\n⚠️ Некоторые поля отсутствуют. Попробуйте перезапустить приложение.")
    
    conn.commit()
    cursor.close()
    conn.close()
    
    print("\n" + "="*60)
    print("ГОТОВО! Теперь перезапустите приложение:")
    print("python app.py")
    print("="*60)

if __name__ == "__main__":
    fix_database()