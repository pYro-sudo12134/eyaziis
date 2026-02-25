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


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)