$(document).ready(function() {
    var tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    var tooltipList = tooltipTriggerList.map(function(tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl);
    });
    
    setTimeout(function() {
        $('.alert').fadeOut('slow');
    }, 5000);
    
    $('.json-viewer').each(function() {
        try {
            var json = JSON.parse($(this).text());
            $(this).text(JSON.stringify(json, null, 2));
        } catch(e) {
        }
    });
    
    $('#quick-search').keypress(function(e) {
        if (e.which == 13) {
            e.preventDefault();
            var query = $(this).val();
            if (query) {
                window.location.href = '/search?q=' + encodeURIComponent(query);
            }
        }
    });
});

function copyToClipboard(text) {
    navigator.clipboard.writeText(text).then(function() {
        showNotification('Скопировано в буфер обмена', 'success');
    }, function(err) {
        showNotification('Ошибка копирования', 'error');
    });
}

function showNotification(message, type) {
    var notification = $('<div class="alert alert-' + (type === 'error' ? 'danger' : type) + ' alert-dismissible fade show" role="alert">' +
        message +
        '<button type="button" class="btn-close" data-bs-dismiss="alert"></button>' +
        '</div>');
    
    $('main').prepend(notification);
    
    setTimeout(function() {
        notification.fadeOut('slow', function() {
            $(this).remove();
        });
    }, 3000);
}

function uploadFileWithProgress(formData, url, progressCallback) {
    $.ajax({
        xhr: function() {
            var xhr = new window.XMLHttpRequest();
            xhr.upload.addEventListener('progress', function(e) {
                if (e.lengthComputable) {
                    var percent = Math.round((e.loaded / e.total) * 100);
                    progressCallback(percent);
                }
            }, false);
            return xhr;
        },
        url: url,
        type: 'POST',
        data: formData,
        processData: false,
        contentType: false,
        success: function(response) {
            showNotification('Файл успешно загружен', 'success');
            setTimeout(function() {
                window.location.href = '/corpus';
            }, 1500);
        },
        error: function(xhr, status, error) {
            showNotification('Ошибка загрузки: ' + error, 'error');
        }
    });
}

function analyzeWord(word) {
    return $.ajax({
        url: '/analyze',
        type: 'POST',
        contentType: 'application/json',
        data: JSON.stringify({word: word}),
        dataType: 'json'
    });
}

function formatNumber(num) {
    return num.toString().replace(/(\d)(?=(\d{3})+(?!\d))/g, '$1 ');
}

function createChart(elementId, data, layout) {
    Plotly.newPlot(elementId, data, layout, {responsive: true});
}

function exportTableToCSV(tableId, filename) {
    var csv = [];
    var rows = document.getElementById(tableId).querySelectorAll('tr');
    
    for (var i = 0; i < rows.length; i++) {
        var row = [], cols = rows[i].querySelectorAll('td, th');
        
        for (var j = 0; j < cols.length; j++) {
            var text = cols[j].innerText.replace(/"/g, '""');
            row.push('"' + text + '"');
        }
        
        csv.push(row.join(','));
    }
    
    var csvFile = new Blob([csv.join('\n')], {type: 'text/csv'});
    var downloadLink = document.createElement('a');
    downloadLink.download = filename;
    downloadLink.href = window.URL.createObjectURL(csvFile);
    downloadLink.style.display = 'none';
    document.body.appendChild(downloadLink);
    downloadLink.click();
}

function validateFile(file) {
    const maxSize = 16 * 1024 * 1024;
    const allowedTypes = ['.txt', '.rtf'];
    
    if (file.size > maxSize) {
        return {
            valid: false,
            message: 'Файл слишком большой. Максимальный размер: 16 МБ'
        };
    }
    
    const fileName = file.name.toLowerCase();
    const isValidType = allowedTypes.some(ext => fileName.endsWith(ext));
    
    if (!isValidType) {
        return {
            valid: false,
            message: 'Неподдерживаемый формат. Разрешены: TXT, RTF'
        };
    }
    
    return { valid: true };
}

function previewFileContent(file) {
    const reader = new FileReader();
    
    reader.onload = function(e) {
        const content = e.target.result;
        const previewLength = 500;
        const preview = content.length > previewLength 
            ? content.substring(0, previewLength) + '...' 
            : content;
        
        const modalHtml = `
            <div class="modal fade" id="previewModal" tabindex="-1">
                <div class="modal-dialog modal-lg">
                    <div class="modal-content">
                        <div class="modal-header">
                            <h5 class="modal-title">Предпросмотр файла</h5>
                            <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                        </div>
                        <div class="modal-body">
                            <pre style="max-height: 400px; overflow-y: auto;">${escapeHtml(preview)}</pre>
                        </div>
                    </div>
                </div>
            </div>
        `;
        
        $('body').append(modalHtml);
        $('#previewModal').modal('show');
        $('#previewModal').on('hidden.bs.modal', function() {
            $(this).remove();
        });
    };
    
    reader.readAsText(file, 'UTF-8');
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function autoFillMetadata() {
    const fileInput = document.getElementById('fileInput');
    if (fileInput.files.length === 0) return;
    
    const fileName = fileInput.files[0].name;
    const title = fileName.replace(/\.[^/.]+$/, "");
    
    if (!document.getElementById('title').value) {
        document.getElementById('title').value = title;
    }
    
    const yearMatch = title.match(/\b(19|20)\d{2}\b/);
    if (yearMatch && !document.getElementById('year').value) {
        document.getElementById('year').value = yearMatch[0];
    }
    
    const authorPatterns = [
        /[А-Я][а-я]+\s[А-Я]\.\s[А-Я]\./,  // Иванов И.И.
        /[А-Я][а-я]+\s[А-Я][а-я]+/,        // Иванов Иван
        /[A-Z][a-z]+\s[A-Z]\.\s[A-Z]\./    // Ivanov I.I.
    ];
    
    for (const pattern of authorPatterns) {
        const match = title.match(pattern);
        if (match && !document.getElementById('author').value) {
            document.getElementById('author').value = match[0];
            break;
        }
    }
    
    updateMetadataPreview();
}

function countWords(text) {
    const words = text.match(/[а-яА-ЯёЁa-zA-Z]+/g) || [];
    return words.length;
}

function detectGenre(text) {
    const lowerText = text.toLowerCase();
    
    const genrePatterns = {
        'научный': ['исследование', 'эксперимент', 'анализ', 'данные', 'результат'],
        'научно-популярный': ['интересно', 'факт', 'ученые', 'открытие', 'удивительно'],
        'художественный': ['был', 'стал', 'сказал', 'думал', 'чувствовал'],
        'публицистический': ['проблема', 'общество', 'власть', 'страна', 'люди'],
        'учебный': ['тема', 'урок', 'задание', 'вопрос', 'ответ'],
        'справочный': ['термин', 'определение', 'понятие', 'классификация'],
        'энциклопедический': ['вид', 'род', 'семейство', 'отряд', 'класс']
    };
    
    let maxMatches = 0;
    let detectedGenre = '';
    
    for (const [genre, patterns] of Object.entries(genrePatterns)) {
        const matches = patterns.filter(pattern => lowerText.includes(pattern)).length;
        if (matches > maxMatches) {
            maxMatches = matches;
            detectedGenre = genre;
        }
    }
    
    return detectedGenre;
}

function saveMetadataToStorage() {
    const metadata = {
        title: document.getElementById('title').value,
        author: document.getElementById('author').value,
        year: document.getElementById('year').value,
        genre: document.getElementById('genre').value,
        source: document.getElementById('source').value
    };
    
    localStorage.setItem('lastMetadata', JSON.stringify(metadata));
}

function loadLastMetadata() {
    const saved = localStorage.getItem('lastMetadata');
    if (saved) {
        try {
            const metadata = JSON.parse(saved);
            document.getElementById('title').value = metadata.title || '';
            document.getElementById('author').value = metadata.author || '';
            document.getElementById('year').value = metadata.year || '';
            document.getElementById('genre').value = metadata.genre || '';
            document.getElementById('source').value = metadata.source || '';
            updateMetadataPreview();
        } catch(e) {}
    }
}

$(document).ready(function() {
    if (window.location.pathname === '/upload') {
        loadLastMetadata();
    }
});

function cancelUpload() {
    if (confirm('Отменить загрузку?')) {
        window.location.href = '/corpus';
    }
}