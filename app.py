import os
import sqlite3
from flask import Flask, render_template, request, redirect, send_from_directory, url_for, session, flash

app = Flask(__name__)
app.secret_key = 'your_secret_key'
app.config['UPLOAD_FOLDER'] = 'uploads'

# Ensure folders exist
os.makedirs('uploads', exist_ok=True)
os.makedirs('database', exist_ok=True)

# Initialize database
def init_db():
    with sqlite3.connect('database/events.db') as conn:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT,
                date TEXT,
                academic_year TEXT,
                category TEXT,
                coordinator TEXT,
                cocoordinator TEXT,
                department TEXT,
                program TEXT,
                participants INTEGER,
                report_filename TEXT
            )
        ''')
init_db()

# Login
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        role = request.form['role']

        if role == 'admin' and username == 'admin' and password == 'admin123':
            session['user'] = username
            session['role'] = 'admin'
            return redirect(url_for('view_records'))
        elif role == 'user' and username == 'user' and password == 'user123':
            session['user'] = username
            session['role'] = 'user'
            return redirect(url_for('index'))
        else:
            flash("Invalid credentials", "danger")
    return render_template('login.html')

# Logout
@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# Upload Page – User Only
@app.route('/', methods=['GET', 'POST'])
def index():
    if 'role' not in session or session['role'] != 'user':
        return redirect(url_for('login'))

    if request.method == 'POST':
        required_fields = ['name', 'date', 'academic_year', 'category', 'coordinator',
                           'cocoordinator', 'department', 'program', 'participants']
        missing_fields = [field for field in required_fields if not request.form.get(field)]
        
        if 'report' not in request.files or request.files['report'].filename == '':
            missing_fields.append('report')

        if missing_fields:
            flash("Please fill in all required fields before submitting the form.", "danger")
            return redirect(url_for('index'))

        data = {
            'name': request.form['name'],
            'date': request.form['date'],
            'academic_year': request.form['academic_year'],
            'category': request.form.get('category', ''),
            'coordinator': request.form['coordinator'],
            'cocoordinator': request.form['cocoordinator'],
            'department': request.form['department'],
            'program': request.form['program'],
            'participants': request.form['participants'],
        }

        file = request.files['report']
        filename = file.filename

        # Save to category folder
        category_folder = os.path.join(app.config['UPLOAD_FOLDER'], data['category'])
        os.makedirs(category_folder, exist_ok=True)

        filepath = os.path.join(category_folder, filename)
        file.save(filepath)

        relative_path = os.path.join(data['category'], filename)

        with sqlite3.connect('database/events.db') as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO events 
                (name, date, academic_year, category, coordinator, cocoordinator, department, program, participants, report_filename)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (data['name'], data['date'], data['academic_year'], data['category'], data['coordinator'],
                  data['cocoordinator'], data['department'], data['program'], data['participants'], relative_path))

        flash("Event uploaded successfully!", "success")
        return redirect(url_for('index'))

    return render_template('index.html')


# View Records – Admin Only
@app.route('/records', methods=['GET', 'POST'])
def view_records():
    if 'role' not in session or session['role'] != 'admin':
        return redirect(url_for('login'))

    query = ""
    if request.method == 'POST':
        query = request.form['search'].strip()

    with sqlite3.connect('database/events.db') as conn:
        cursor = conn.cursor()
        if query:
            cursor.execute("""
                SELECT * FROM events 
                WHERE name LIKE ? OR category LIKE ? OR academic_year LIKE ? OR coordinator LIKE ?
            """, (f'%{query}%', f'%{query}%', f'%{query}%', f'%{query}%'))
        else:
            cursor.execute("SELECT * FROM events")
        events = cursor.fetchall()

    return render_template('view.html', events=events, query=query)

# Delete Record – Admin Only
@app.route('/delete/<int:id>')
def delete_record(id):
    if 'role' not in session or session['role'] != 'admin':
        return redirect(url_for('login'))

    with sqlite3.connect('database/events.db') as conn:
        cursor = conn.cursor()

        # Delete file
        filename = cursor.execute('SELECT report_filename FROM events WHERE id = ?', (id,)).fetchone()
        if filename and os.path.exists(os.path.join(app.config['UPLOAD_FOLDER'], filename[0])):
            os.remove(os.path.join(app.config['UPLOAD_FOLDER'], filename[0]))

        # Delete record
        cursor.execute('DELETE FROM events WHERE id = ?', (id,))

        # Rebuild table and reindex
        cursor.execute('CREATE TEMP TABLE events_backup AS SELECT * FROM events')
        cursor.execute('DROP TABLE events')
        cursor.execute('''
            CREATE TABLE events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT,
                date TEXT,
                academic_year TEXT,
                category TEXT,
                coordinator TEXT,
                cocoordinator TEXT,
                department TEXT,
                program TEXT,
                participants INTEGER,
                report_filename TEXT
            )
        ''')
        cursor.execute('''
            INSERT INTO events (name, date, academic_year, category, coordinator, cocoordinator, department, program, participants, report_filename)
            SELECT name, date, academic_year, category, coordinator, cocoordinator, department, program, participants, report_filename
            FROM events_backup
        ''')
        cursor.execute('DROP TABLE events_backup')

    flash("Record deleted successfully and IDs reindexed.", "info")
    return redirect(url_for('view_records'))

# Download – Admin Only
@app.route('/uploads/<path:filename>')
def download_file(filename):
    if 'role' not in session or session['role'] != 'admin':
        return redirect(url_for('login'))
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename, as_attachment=True)

# Run App
if __name__ == '__main__':
    app.run(debug=True)
