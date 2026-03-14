from flask import Flask, render_template, request, jsonify, session, redirect, url_for, flash
from flask import send_file
import os
import json
from datetime import datetime
import plotly
import plotly.graph_objs as go
import pandas as pd
from psycopg2.extras import DictCursor
from database import PostgreSQLConnection
from corpus_manager import CorpusManager
from morphology_analyzer import get_morphology_analyzer
from syntax_analyzer import get_syntax_analyzer

app = Flask(__name__)
app.secret_key = 'your-secret-key-here'
app.config['UPLOAD_FOLDER'] = 'corpus/animals'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

try:
    print("Подключение к PostgreSQL...")
    db_connection = PostgreSQLConnection()
    db_connection.connect()
    print("Подключение к БД успешно установлено")
    
    corpus_manager = CorpusManager(db_connection)
    morph_analyzer = get_morphology_analyzer()
    print("Корпусный менеджер инициализирован")
except Exception as e:
    print(f"ОШИБКА подключения к БД: {e}")
    print("Проверьте, запущен ли PostgreSQL (docker ps)")
    exit(1)


@app.route('/')
def index():
    """Главная страница"""
    return render_template('index.html')


@app.route('/corpus')
def corpus_view():
    """Просмотр корпуса"""
    domain = request.args.get('domain', 'animals')
    documents = corpus_manager.get_documents(domain)
    
    for doc in documents:
        try:
            cursor = db_connection.connection.cursor()
            cursor.execute("""
                SELECT COUNT(*) FROM public.sentences 
                WHERE document_id = %s
            """, (doc['id'],))
            doc['sentence_count'] = cursor.fetchone()[0]
            cursor.close()
        except:
            doc['sentence_count'] = 0
    
    stats = corpus_manager.get_statistics(domain)
    
    return render_template('corpus.html', documents=documents, domain=domain, stats=stats)

@app.route('/document/<int:doc_id>')
def view_document(doc_id):
    """Просмотр конкретного документа"""
    try:
        cursor = db_connection.connection.cursor(cursor_factory=DictCursor)
        
        cursor.execute("""
            SELECT * FROM public.documents WHERE id = %s
        """, (doc_id,))
        document = dict(cursor.fetchone())
        
        cursor.execute("""
            SELECT * FROM public.sentences 
            WHERE document_id = %s 
            ORDER BY sentence_index
            LIMIT 100
        """, (doc_id,))
        sentences = [dict(row) for row in cursor.fetchall()]
        
        cursor.close()
        
        return render_template('document.html', document=document, sentences=sentences)
        
    except Exception as e:
        flash(f'Ошибка загрузки документа: {e}', 'error')
        return redirect(url_for('corpus_view'))

@app.route('/search', methods=['GET', 'POST'])
def search():
    """Поиск в корпусе"""
    if request.method == 'POST':
        query = request.form.get('query', '')
        search_type = request.form.get('search_type', 'word_form')
        
        filters = {
            'domain': request.form.get('domain', 'animals'),
            'genre': request.form.get('genre'),
            'author': request.form.get('author'),
            'year_from': request.form.get('year_from'),
            'year_to': request.form.get('year_to')
        }
        
        filters = {k: v for k, v in filters.items() if v}
        
        results = corpus_manager.search(query, search_type, filters)
        
        print(f"Поиск: '{query}', тип: {search_type}")
        print(f"Найдено результатов: {results.get('total', 0)}")
        if results.get('items'):
            print(f"Первый результат: {results['items'][0] if results['items'] else 'Нет'}")
        
        return render_template('search_results.html', results=results)
    
    return render_template('search.html')


@app.route('/concordance/<word>')
def concordance(word):
    """Просмотр конкорданса для слова"""
    results = corpus_manager.get_concordance(word)
    return render_template('concordance.html', word=word, results=results)


@app.route('/statistics')
def statistics():
    """Статистика корпуса"""
    domain = request.args.get('domain', 'animals')
    stats = corpus_manager.get_statistics(domain)
    
    graphs = []
    
    if stats['morphology'].get('part_of_speech'):
        pos_data = stats['morphology']['part_of_speech']
        if pos_data:
            pos_fig = go.Figure(data=[
                go.Bar(
                    x=[item[0] for item in pos_data],
                    y=[item[1] for item in pos_data],
                    marker_color='rgb(55, 83, 109)'
                )
            ])
            pos_fig.update_layout(
                title='Распределение частей речи',
                xaxis_title='Часть речи',
                yaxis_title='Количество'
            )
            graphs.append(json.dumps(pos_fig, cls=plotly.utils.PlotlyJSONEncoder))
    
    if stats['frequent_words']:
        freq_fig = go.Figure(data=[
            go.Bar(
                x=[item[0] for item in stats['frequent_words'][:20]],
                y=[item[1] for item in stats['frequent_words'][:20]],
                marker_color='rgb(26, 118, 255)'
            )
        ])
        freq_fig.update_layout(
            title='Топ-20 самых частотных слов',
            xaxis_title='Слово',
            yaxis_title='Частота'
        )
        graphs.append(json.dumps(freq_fig, cls=plotly.utils.PlotlyJSONEncoder))
    
    return render_template('statistics.html', stats=stats, graphs=graphs)


@app.route('/upload', methods=['GET', 'POST'])
def upload_document():
    """Загрузка документа в корпус"""
    if request.method == 'POST':
        if 'file' not in request.files:
            flash('Файл не выбран', 'error')
            return redirect(request.url)
        
        file = request.files['file']
        
        if file.filename == '':
            flash('Файл не выбран', 'error')
            return redirect(request.url)
        
        if file:
            filename = file.filename
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)
            
            metadata = {
                'title': request.form.get('title', filename),
                'author': request.form.get('author'),
                'year': request.form.get('year', type=int),
                'genre': request.form.get('genre'),
                'source': request.form.get('source')
            }
            
            results = corpus_manager.process_document(filepath, metadata)
            
            if results['success']:
                flash(f'Документ успешно загружен. Предложений: {results["sentences_count"]}, слов: {results["tokens_count"]}', 'success')
            else:
                flash(f'Ошибка загрузки: {", ".join(results["errors"])}', 'error')
            
            return redirect(url_for('corpus_view'))
    
    return render_template('upload.html')


@app.route('/analyze', methods=['POST'])
def analyze_word():
    """Анализ слова (AJAX)"""
    data = request.get_json()
    word = data.get('word', '')
    
    if not word:
        return jsonify({'error': 'Слово не указано'})
    
    analysis = morph_analyzer.analyze_word(word)
    return jsonify(analysis)


@app.route('/api/search')
def api_search():
    """API для поиска"""
    query = request.args.get('q', '')
    search_type = request.args.get('type', 'word_form')
    domain = request.args.get('domain', 'animals')
    
    results = corpus_manager.search(query, search_type, {'domain': domain})
    return jsonify(results)


@app.route('/api/statistics')
def api_statistics():
    """API для статистики"""
    domain = request.args.get('domain', 'animals')
    stats = corpus_manager.get_statistics(domain)
    return jsonify(stats)


@app.route('/export')
def export_statistics():
    """Экспорт статистики"""
    format = request.args.get('format', 'json')
    domain = request.args.get('domain', 'animals')
    
    stats = corpus_manager.export_corpus_stats(format)
    
    if format == 'json':
        return jsonify(stats)
    elif format == 'csv':
        df = pd.DataFrame(stats['frequent_words'], columns=['word', 'frequency'])
        csv_data = df.to_csv(index=False)
        
        temp_file = f'temp_stats_{datetime.now().timestamp()}.csv'
        with open(temp_file, 'w', encoding='utf-8') as f:
            f.write(csv_data)
        
        return send_file(temp_file, as_attachment=True, 
                        download_name=f'corpus_stats_{domain}.csv')
    
    return jsonify({'error': 'Неподдерживаемый формат'})

@app.route('/api/validate-file', methods=['POST'])
def api_validate_file():
    """API для валидации файла перед загрузкой"""
    if 'file' not in request.files:
        return jsonify({'valid': False, 'error': 'Файл не найден'})
    
    file = request.files['file']
    
    file.seek(0, 2)
    size = file.tell()
    file.seek(0)
    
    if size > 16 * 1024 * 1024:
        return jsonify({'valid': False, 'error': 'Файл слишком большой (макс. 16 МБ)'})
    
    filename = file.filename.lower()
    supported_formats = ['.txt', '.rtf', '.pdf', '.docx', '.doc']
    
    if not any(filename.endswith(fmt) for fmt in supported_formats):
        return jsonify({
            'valid': False, 
            'error': f'Неподдерживаемый формат. Поддерживаются: {", ".join(supported_formats)}'
        })
    
    try:
        content = file.read(1024).decode('utf-8', errors='ignore')
        word_count = len(content.split())
        file.seek(0)
        
        return jsonify({
            'valid': True,
            'size': size,
            'word_count': word_count,
            'preview': content[:200] + '...' if len(content) > 200 else content
        })
    except Exception as e:
        return jsonify({'valid': False, 'error': str(e)})

@app.route('/api/upload-progress', methods=['GET'])
def upload_progress():
    """API для получения прогресса загрузки (WebSocket альтернатива)"""
    session_id = request.args.get('session_id')
    if session_id and session_id in upload_progress_data:
        return jsonify(upload_progress_data[session_id])
    return jsonify({'progress': 0, 'status': 'unknown'})

upload_progress_data = {}

@app.route('/help')
def help_page():
    """Справка"""
    return render_template('help.html')


@app.errorhandler(404)
def not_found_error(error):
    """Обработчик 404 ошибки"""
    return render_template('404.html'), 404

@app.errorhandler(500)
def internal_error(error):
    """Обработчик 500 ошибки"""
    try:
        db_connection.connection.rollback()
    except:
        pass
    return render_template('500.html'), 500

@app.route('/syntax/sentence/<int:sentence_id>')
def view_sentence_syntax(sentence_id):
    """Просмотр синтаксического разбора предложения"""
    try:
        # Получаем предложение
        cursor = db_connection.connection.cursor(cursor_factory=DictCursor)
        cursor.execute("""
            SELECT s.*, d.title as document_title, d.id as document_id
            FROM public.sentences s
            JOIN public.documents d ON s.document_id = d.id
            WHERE s.id = %s
        """, (sentence_id,))
        sentence = dict(cursor.fetchone())
        cursor.close()
        
        # Получаем синтаксическую информацию
        syntax_data = corpus_manager.get_sentence_syntax(sentence_id)
        
        # Получаем токены для отображения
        cursor = db_connection.connection.cursor(cursor_factory=DictCursor)
        cursor.execute("""
            SELECT t.*, wf.word_form, 
                   m.part_of_speech, m.gender, m.number, m.case_form, m.normal_form
            FROM public.tokens t
            LEFT JOIN public.word_forms wf ON t.word_form_id = wf.id
            LEFT JOIN public.morphology m ON wf.id = m.word_form_id
            WHERE t.sentence_id = %s
            ORDER BY t.token_index
        """, (sentence_id,))
        tokens = [dict(row) for row in cursor.fetchall()]
        cursor.close()
        
        # ОТЛАДКА: печатаем первый токен, чтобы увидеть структуру
        if tokens:
            print("Первый токен:", tokens[0])
            print("Ключи токена:", tokens[0].keys())
        
        return render_template(
            'sentence_syntax.html',
            sentence=sentence,
            tokens=tokens,
            syntax=syntax_data
        )
        
    except Exception as e:
        flash(f'Ошибка загрузки синтаксиса: {e}', 'error')
        return redirect(url_for('corpus_view'))

@app.route('/syntax/document/<int:doc_id>')
def view_document_syntax(doc_id):
    """Просмотр синтаксического разбора всего документа"""
    try:
        # Получаем документ
        cursor = db_connection.connection.cursor(cursor_factory=DictCursor)
        cursor.execute("""
            SELECT * FROM public.documents WHERE id = %s
        """, (doc_id,))
        document = dict(cursor.fetchone())
        
        # Получаем предложения с синтаксическим анализом
        cursor.execute("""
            SELECT s.id, s.sentence_text, s.sentence_index,
                   s.syntax_analyzed,
                   COUNT(DISTINCT sr.id) as relation_count,
                   COUNT(DISTINCT sp.id) as part_count
            FROM public.sentences s
            LEFT JOIN public.syntax_relations sr ON s.id = sr.sentence_id
            LEFT JOIN public.sentence_parts sp ON s.id = sp.sentence_id
            WHERE s.document_id = %s
            GROUP BY s.id, s.sentence_text, s.sentence_index, s.syntax_analyzed
            ORDER BY s.sentence_index
        """, (doc_id,))
        sentences = [dict(row) for row in cursor.fetchall()]
        cursor.close()
        
        # Статистика по документу
        stats = {
            'total_sentences': len(sentences),
            'analyzed': sum(1 for s in sentences if s['syntax_analyzed']),
            'avg_relations': sum(s['relation_count'] or 0 for s in sentences) / len(sentences) if sentences else 0
        }
        
        return render_template(
            'document_syntax.html',
            document=document,
            sentences=sentences,
            stats=stats
        )
        
    except Exception as e:
        flash(f'Ошибка загрузки: {e}', 'error')
        return redirect(url_for('corpus_view'))

@app.route('/syntax/analyze/<int:doc_id>', methods=['POST'])
def analyze_document_syntax(doc_id):
    """Запуск синтаксического анализа документа"""
    try:
        results = corpus_manager.analyze_document_syntax(doc_id)
        
        if results['failed'] == 0:
            flash(f'Синтаксический анализ завершен. Проанализировано предложений: {results["analyzed"]}', 'success')
        else:
            flash(f'Анализ завершен с ошибками. Успешно: {results["analyzed"]}, ошибок: {results["failed"]}', 'warning')
        
        return jsonify(results)
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/syntax/search')
def syntax_search():
    """Поиск по синтаксическим конструкциям"""
    # Получаем параметры из запроса
    relation = request.args.get('relation', '')
    head_pos = request.args.get('head_pos', '')
    dep_pos = request.args.get('dep_pos', '')
    domain = request.args.get('domain', 'animals')
    
    print(f"=== СИНТАКСИЧЕСКИЙ ПОИСК ===")
    print(f"relation: {relation}")
    print(f"head_pos: {head_pos}")
    print(f"dep_pos: {dep_pos}")
    print(f"domain: {domain}")
    
    pattern = {}
    # Если relation не указан или пустой, ищем все отношения
    if relation and relation.strip():  # если выбрана конкретная связь
        pattern['relation_type'] = relation
    # иначе pattern остается пустым - будем искать все
    
    if head_pos:
        pattern['head_pos'] = head_pos
    if dep_pos:
        pattern['dependent_pos'] = dep_pos
    
    results = []
    # Всегда выполняем поиск, даже если pattern пустой
    # Пустой pattern означает поиск всех отношений
    print(f"Поиск по шаблону: {pattern}")
    results = corpus_manager.search_by_syntax(pattern, domain)
    print(f"Найдено результатов: {len(results)}")
    if results:
        print(f"Первый результат: {results[0]}")
    
    # Получаем список доступных типов отношений для формы
    relation_types = []
    try:
        cursor = db_connection.connection.cursor()
        cursor.execute("""
            SELECT DISTINCT relation_type, relation_name 
            FROM public.syntax_relations 
            ORDER BY relation_type
        """)
        rows = cursor.fetchall()
        relation_types = [{'type': row[0], 'name': row[1] or row[0]} for row in rows]
        cursor.close()
        print(f"Загружено типов отношений: {len(relation_types)}")
    except Exception as e:
        print(f"Ошибка загрузки типов отношений: {e}")
    
    # ВАЖНО: передаем results в шаблон
    return render_template(
        'syntax_search.html',
        results=results,
        relation_types=relation_types,
        selected_relation=relation,
        selected_head_pos=head_pos,
        selected_dep_pos=dep_pos
    )

@app.route('/debug/syntax-relations')
def debug_syntax_relations():
    """Проверка синтаксических отношений в БД"""
    try:
        cursor = db_connection.connection.cursor(cursor_factory=DictCursor)
        
        cursor.execute("""
            SELECT COUNT(*) FROM public.syntax_relations
        """)
        total = cursor.fetchone()[0]
        
        cursor.execute("""
            SELECT relation_type, COUNT(*) as cnt
            FROM public.syntax_relations
            GROUP BY relation_type
            ORDER BY cnt DESC
        """)
        types = cursor.fetchall()
        
        cursor.execute("""
            SELECT sr.*, LEFT(s.sentence_text, 50) as sentence_preview
            FROM public.syntax_relations sr
            JOIN public.sentences s ON sr.sentence_id = s.id
            LIMIT 10
        """)
        examples = cursor.fetchall()
        
        cursor.close()
        
        html = f"<h1>Синтаксические отношения</h1>"
        html += f"<p>Всего отношений: {total}</p>"
        
        html += "<h2>Типы отношений:</h2><ul>"
        for t in types:
            html += f"<li>{t['relation_type']}: {t['cnt']}</li>"
        html += "</ul>"
        
        html += "<h2>Примеры:</h2>"
        for ex in examples:
            html += f"<p>{ex['sentence_preview']}... - {ex['head_token_id']} -> {ex['dependent_token_id']} ({ex['relation_type']})</p>"
        
        return html
    except Exception as e:
        return f"Ошибка: {e}"

@app.route('/api/syntax/visualize/<int:sentence_id>')
def api_syntax_visualize(sentence_id):
    """API для получения данных визуализации"""
    try:
        syntax_data = corpus_manager.get_sentence_syntax(sentence_id)
        
        # Для отладки - посмотрим, что приходит
        print("syntax_data keys:", syntax_data.keys())
        if syntax_data.get('relations'):
            print("First relation:", syntax_data['relations'][0] if syntax_data['relations'] else "None")
        
        # Получаем токены для узлов
        cursor = db_connection.connection.cursor(cursor_factory=DictCursor)
        cursor.execute("""
            SELECT id, token_text, token_index
            FROM public.tokens
            WHERE sentence_id = %s
            ORDER BY token_index
        """, (sentence_id,))
        tokens = [dict(row) for row in cursor.fetchall()]
        cursor.close()
        
        # Создаем словарь токенов для быстрого доступа
        token_map = {t['id']: t for t in tokens}
        
        # Формируем узлы
        nodes = []
        for token in tokens:
            nodes.append({
                'id': token['id'],
                'label': token['token_text'],
                'index': token['token_index']
            })
        
        # Формируем связи
        links = []
        if syntax_data and 'relations' in syntax_data:
            for rel in syntax_data['relations']:
                # Проверяем правильные имена ключей из БД
                head_id = rel.get('head_id') or rel.get('head_token_id')
                dep_id = rel.get('dependent_id') or rel.get('dependent_token_id')
                
                if head_id and dep_id and head_id in token_map and dep_id in token_map:
                    links.append({
                        'source': head_id,
                        'target': dep_id,
                        'type': rel.get('relation_type', 'unknown'),
                        'name': rel.get('relation_name', rel.get('relation_type', 'unknown'))
                    })
        
        print(f"Nodes: {len(nodes)}, Links: {len(links)}")
        
        return jsonify({
            'nodes': nodes,
            'links': links
        })
        
    except Exception as e:
        print(f"Ошибка визуализации: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/debug/tables')
def debug_tables():
    try:
        cursor = db_connection.connection.cursor()
        
        # Получаем список всех таблиц
        cursor.execute("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public'
            ORDER BY table_name;
        """)
        tables = cursor.fetchall()
        
        # Для каждой таблицы получаем структуру
        result = "<h1>Таблицы в базе данных:</h1>"
        for table in tables:
            table_name = table[0]
            result += f"<h2>{table_name}</h2>"
            
            # Получаем колонки таблицы
            cursor.execute("""
                SELECT column_name, data_type, is_nullable
                FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = %s
                ORDER BY ordinal_position;
            """, (table_name,))
            columns = cursor.fetchall()
            
            result += "<table border='1'><tr><th>Колонка</th><th>Тип</th><th>Nullable</th></tr>"
            for col in columns:
                result += f"<tr><td>{col[0]}</td><td>{col[1]}</td><td>{col[2]}</td></tr>"
            result += "</table><br>"
        
        cursor.close()
        return result
    except Exception as e:
        return f"Ошибка: {e}"
        
@app.route('/debug/morphology/<int:sentence_id>')
def debug_morphology(sentence_id):
    """Проверка морфологии для предложения"""
    try:
        cursor = db_connection.connection.cursor(cursor_factory=DictCursor)
        
        # Проверяем токены с морфологией
        cursor.execute("""
            SELECT t.id, t.token_text, wf.word_form, 
                   m.part_of_speech, m.gender, m.number, m.case_form, m.normal_form
            FROM public.tokens t
            LEFT JOIN public.word_forms wf ON t.word_form_id = wf.id
            LEFT JOIN public.morphology m ON wf.id = m.word_form_id
            WHERE t.sentence_id = %s
            ORDER BY t.token_index
        """, (sentence_id,))
        
        tokens = cursor.fetchall()
        cursor.close()
        
        result = "<h1>Морфология для предложения</h1><table border='1'>"
        result += "<tr><th>Token</th><th>Word Form</th><th>POS</th><th>Gender</th><th>Number</th><th>Case</th><th>Lemma</th></tr>"
        
        for token in tokens:
            result += f"<tr>"
            result += f"<td>{token[1]}</td>"
            result += f"<td>{token[2] or '-'}</td>"
            result += f"<td>{token[3] or '-'}</td>"
            result += f"<td>{token[4] or '-'}</td>"
            result += f"<td>{token[5] or '-'}</td>"
            result += f"<td>{token[6] or '-'}</td>"
            result += f"<td>{token[7] or '-'}</td>"
            result += f"</tr>"
        
        result += "</table>"
        return result
        
    except Exception as e:
        return f"Ошибка: {e}"

@app.route('/debug/syntax/<int:sentence_id>')
def debug_syntax(sentence_id):
    """Отладка синтаксических данных"""
    try:
        cursor = db_connection.connection.cursor(cursor_factory=DictCursor)
        
        # Проверяем отношения
        cursor.execute("""
            SELECT COUNT(*) FROM public.syntax_relations 
            WHERE sentence_id = %s
        """, (sentence_id,))
        relations_count = cursor.fetchone()[0]
        
        # Проверяем группы
        cursor.execute("""
            SELECT COUNT(*) FROM public.syntax_groups 
            WHERE sentence_id = %s
        """, (sentence_id,))
        groups_count = cursor.fetchone()[0]
        
        # Проверяем члены предложения
        cursor.execute("""
            SELECT COUNT(*) FROM public.sentence_parts 
            WHERE sentence_id = %s
        """, (sentence_id,))
        parts_count = cursor.fetchone()[0]
        
        # Проверяем дерево
        cursor.execute("""
            SELECT COUNT(*) FROM public.parse_trees 
            WHERE sentence_id = %s
        """, (sentence_id,))
        tree_count = cursor.fetchone()[0]
        
        cursor.close()
        
        return jsonify({
            'sentence_id': sentence_id,
            'relations_count': relations_count,
            'groups_count': groups_count,
            'parts_count': parts_count,
            'tree_count': tree_count,
            'has_data': relations_count > 0 or groups_count > 0 or parts_count > 0
        })
    except Exception as e:
        return jsonify({'error': str(e)})

@app.route('/debug/check-data')
def debug_check_data():
    """Проверка наличия данных для поиска"""
    try:
        cursor = db_connection.connection.cursor()
        result = "<h1>Проверка данных для поиска</h1>"
        
        # Проверяем документы
        cursor.execute("SELECT COUNT(*) FROM public.documents")
        docs_count = cursor.fetchone()[0]
        result += f"<p><b>Документов:</b> {docs_count}</p>"
        
        # Проверяем предложения
        cursor.execute("SELECT COUNT(*) FROM public.sentences")
        sentences_count = cursor.fetchone()[0]
        result += f"<p><b>Предложений:</b> {sentences_count}</p>"
        
        # Проверяем токены
        cursor.execute("SELECT COUNT(*) FROM public.tokens")
        tokens_count = cursor.fetchone()[0]
        result += f"<p><b>Токенов:</b> {tokens_count}</p>"
        
        # Проверяем словоформы
        cursor.execute("SELECT COUNT(*) FROM public.word_forms")
        word_forms_count = cursor.fetchone()[0]
        result += f"<p><b>Словоформ:</b> {word_forms_count}</p>"
        
        # Проверяем морфологию
        cursor.execute("SELECT COUNT(*) FROM public.morphology")
        morph_count = cursor.fetchone()[0]
        result += f"<p><b>Морфология:</b> {morph_count}</p>"
        
        # Показываем несколько примеров словоформ
        cursor.execute("""
            SELECT wf.word_form, m.normal_form, m.part_of_speech 
            FROM public.word_forms wf
            LEFT JOIN public.morphology m ON wf.id = m.word_form_id
            LIMIT 10
        """)
        examples = cursor.fetchall()
        
        result += "<h2>Примеры словоформ:</h2><ul>"
        for ex in examples:
            result += f"<li>{ex[0]} -> {ex[1] or '?'} ({ex[2] or '?'})</li>"
        result += "</ul>"
        
        cursor.close()
        return result
    except Exception as e:
        return f"Ошибка: {str(e)}"

@app.route('/debug/test-syntax-search')
def debug_test_syntax_search():
    """Тестирование синтаксического поиска"""
    try:
        # Простой тестовый запрос - поиск всех подлежащих
        pattern = {'relation_type': 'nsubj'}
        results = corpus_manager.search_by_syntax(pattern, 'animals')
        
        html = "<h1>Тест синтаксического поиска</h1>"
        html += f"<p>Запрос: nsubj</p>"
        html += f"<p>Тип results: {type(results)}</p>"
        html += f"<p>Длина results: {len(results)}</p>"
        
        if results:
            html += "<h2>Первый результат:</h2>"
            first = results[0]
            html += f"<p>Тип первого элемента: {type(first)}</p>"
            html += "<pre>"
            import pprint
            html += pprint.pformat(first)
            html += "</pre>"
            
            html += "<h2>Ключи:</h2>"
            if isinstance(first, dict):
                html += "<ul>"
                for key in first.keys():
                    html += f"<li>{key}: {first[key]}</li>"
                html += "</ul>"
            else:
                html += f"<p>Первый элемент не словарь, а {type(first)}</p>"
        else:
            html += "<p>Нет результатов!</p>"
            
            # Проверим, есть ли вообще отношения nsubj
            cursor = db_connection.connection.cursor()
            cursor.execute("""
                SELECT COUNT(*) FROM public.syntax_relations 
                WHERE relation_type = 'nsubj'
            """)
            count = cursor.fetchone()[0]
            cursor.close()
            html += f"<p>Всего отношений nsubj в БД: {count}</p>"
        
        return html
    except Exception as e:
        return f"Ошибка: {e}<br><pre>{traceback.format_exc()}</pre>"

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)