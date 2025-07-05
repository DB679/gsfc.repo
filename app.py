import os, sqlite3
from flask import Flask, render_template, request, redirect, url_for, session, flash, send_from_directory
from werkzeug.security import generate_password_hash, check_password_hash
from uuid import uuid4

app = Flask(__name__)
app.secret_key = 'your_secret_key'
app.config['UPLOAD_FOLDER'] = 'Uploads'
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs('database', exist_ok=True)

# Initialize databases
def init_db():
    try:
        with sqlite3.connect('database/users.db') as conn:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    school TEXT NOT NULL,
                    department TEXT NOT NULL,
                    program TEXT NOT NULL,
                    contact TEXT NOT NULL,
                    email TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    role TEXT NOT NULL
                )''')
            conn.commit()
        with sqlite3.connect('database/events.db') as conn:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT, date TEXT, academic_year TEXT,
                    category TEXT, school TEXT,
                    coordinator TEXT, cocoordinator TEXT,
                    branch TEXT, program TEXT,
                    participants INTEGER, report_filename TEXT,
                    submitted_by TEXT
                )''')
            conn.commit()
        print("DEBUG: Databases initialized successfully.")
    except Exception as e:
        print("INIT DB ERROR:", str(e))

init_db()

# ----------- ROUTES -----------

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        name = request.form['name'].strip()
        school = request.form['school']
        department = request.form['department']
        program = request.form['program']
        contact = request.form['contact'].strip()
        email = request.form['email'].strip().lower()
        password = request.form['password']
        confirm_password = request.form['confirm_password']
        role = request.form['role']

        if password != confirm_password:
            flash('Passwords do not match.', 'danger')
            return redirect(url_for('register'))

        password_hash = generate_password_hash(password)
        try:
            with sqlite3.connect('database/users.db') as conn:
                conn.execute('''
                    INSERT INTO users (name, school, department, program, contact, email, password_hash, role)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
                    (name, school, department, program, contact, email, password_hash, role))
                conn.commit()
            flash('Registration successful! Please log in.', 'success')
            return redirect(url_for('login'))
        except sqlite3.IntegrityError:
            flash('Email already exists.', 'danger')
            return redirect(url_for('register'))
        except Exception as e:
            print("REGISTER ERROR:", str(e))
            flash('Error during registration: ' + str(e), 'danger')
            return redirect(url_for('register'))

    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email'].strip().lower()
        password = request.form['password']
        try:
            with sqlite3.connect('database/users.db') as conn:
                user = conn.execute('SELECT password_hash, role FROM users WHERE email = ?', (email,)).fetchone()
            if user and check_password_hash(user[0], password):
                session['user'] = email
                session['role'] = user[1]
                flash('Login successful!', 'success')
                return redirect(url_for('index'))
            flash('Invalid credentials.', 'danger')
        except Exception as e:
            print("LOGIN ERROR:", str(e))
            flash('Error during login: ' + str(e), 'danger')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out.', 'info')
    return redirect(url_for('login'))

@app.route('/', methods=['GET', 'POST'])
def index():
    if 'role' not in session:
        return redirect(url_for('login'))

    if request.method == 'POST':
        required = ['name', 'date', 'academic_year', 'category', 'school', 'coordinator', 'cocoordinator', 'branch', 'program', 'participants']
        print('DEBUG FORM:', {field: request.form.get(field) for field in required}, 'FILES:', request.files)
        if any(not request.form.get(field) for field in required) or 'report' not in request.files:
            flash('All fields are required.', 'danger')
            return redirect(url_for('index'))

        data = {field: request.form.get(field) for field in required}
        file = request.files['report']
        year_folder = os.path.join(app.config['UPLOAD_FOLDER'], data['academic_year'])
        school_folder = os.path.join(year_folder, data['school'].replace(' ', '_'))
        category_folder = os.path.join(school_folder, data['category'].replace(' ', '_'))
        os.makedirs(category_folder, exist_ok=True)
        file_path = os.path.join(category_folder, file.filename)
        file.save(file_path)

        relative_path = os.path.relpath(file_path, app.config['UPLOAD_FOLDER'])

        try:
            with sqlite3.connect('database/events.db') as conn:
                conn.execute('''
                    INSERT INTO events (
                        name, date, academic_year, category, school,
                        coordinator, cocoordinator, branch, program,
                        participants, report_filename, submitted_by
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                    (*data.values(), relative_path, session['user'])
                )
                conn.commit()
            flash('Event uploaded successfully.', 'success')
        except Exception as e:
            print("DB INSERT ERROR:", str(e))
            flash('Error uploading event: ' + str(e), 'danger')
        return redirect(url_for('index'))

    return render_template('index.html')

@app.route('/records', methods=['GET', 'POST'])
def view_records():
    if 'role' not in session:
        return redirect(url_for('login'))

    query = "SELECT * FROM events WHERE 1=1"
    filters = []
    search = request.form.get('search', '').strip()
    category = request.form.get('category', '')
    school = request.form.get('school', '')
    year = request.form.get('year', '')

    if search:
        query += " AND (name LIKE ? OR academic_year LIKE ? OR coordinator LIKE ?)"
        filters += [f'%{search}%'] * 3

    if category and category != 'All':
        query += " AND category = ?"
        filters.append(category)

    if school and school != 'All':
        query += " AND school = ?"
        filters.append(school)

    if year and year != 'All':
        query += " AND academic_year = ?"
        filters.append(year)

    if session['role'] == 'student':
        query += " AND submitted_by = ?"
        filters.append(session['user'])

    try:
        with sqlite3.connect('database/events.db') as conn:
            events = conn.execute(query, filters).fetchall()
            years = [row[0] for row in conn.execute('SELECT DISTINCT academic_year FROM events ORDER BY academic_year DESC').fetchall()]
        categories = ["All", "Expert talk", "Alumin talk", "Workshop", "Hands on", "Sports", "Hackathon", "Cultural", "Industrial visit"]
        return render_template('view.html', events=events, query=search, selected_category=category, categories=categories, years=years, selected_year=year)
    except Exception as e:
        print("VIEW RECORDS ERROR:", str(e))
        flash('Error loading records: ' + str(e), 'danger')
        return redirect(url_for('index'))

@app.route('/search_suggestions')
def search_suggestions():
    term = request.args.get('q', '').strip()
    suggestions = []
    try:
        if term:
            with sqlite3.connect('database/events.db') as conn:
                rows = conn.execute('SELECT DISTINCT name FROM events WHERE name LIKE ? LIMIT 10', (f'%{term}%',)).fetchall()
                suggestions = [row[0] for row in rows]
        return {'suggestions': suggestions}
    except Exception as e:
        print("SEARCH SUGGESTIONS ERROR:", str(e))
        return {'suggestions': []}

@app.route('/edit/<int:id>', methods=['GET', 'POST'])
def edit(id):
    if session.get('role') not in ('admin', 'faculty'):
        flash('Access restricted to admins or faculty.', 'danger')
        return redirect(url_for('login'))

    try:
        with sqlite3.connect('database/events.db') as conn:
            if request.method == 'POST':
                updated_data = [request.form[field] for field in [
                    'name', 'date', 'academic_year', 'category', 'school',
                    'coordinator', 'cocoordinator', 'branch', 'program', 'participants'
                ]]
                updated_data.append(id)
                conn.execute('''
                    UPDATE events SET
                        name=?, date=?, academic_year=?, category=?, school=?,
                        coordinator=?, cocoordinator=?, branch=?, program=?, participants=?
                    WHERE id=?''', updated_data)
                conn.commit()
                flash('Event updated successfully.', 'success')
                return redirect(url_for('view_records'))

            event = conn.execute('SELECT * FROM events WHERE id = ?', (id,)).fetchone()
            if not event:
                flash('Event not found.', 'danger')
                return redirect(url_for('view_records'))
        return render_template('edit.html', event=event)
    except Exception as e:
        print("EDIT EVENT ERROR:", str(e))
        flash('Error editing event: ' + str(e), 'danger')
        return redirect(url_for('view_records'))

@app.route('/delete/<int:id>')
def delete(id):
    if session.get('role') != 'admin':
        flash('Access restricted to admins.', 'danger')
        return redirect(url_for('login'))

    try:
        with sqlite3.connect('database/events.db') as conn:
            filename = conn.execute('SELECT report_filename FROM events WHERE id = ?', (id,)).fetchone()
            if filename:
                full_path = os.path.join(app.config['UPLOAD_FOLDER'], filename[0])
                if os.path.exists(full_path):
                    os.remove(full_path)
            conn.execute('DELETE FROM events WHERE id = ?', (id,))
            conn.commit()
        flash('Event deleted successfully.', 'info')
    except Exception as e:
        print("DELETE EVENT ERROR:", str(e))
        flash('Error deleting event: ' + str(e), 'danger')
    return redirect(url_for('view_records'))

@app.route('/uploads/<path:filename>')
def download(filename):
    if session.get('role') != 'admin':
        flash('Download not permitted.', 'warning')
        return redirect(url_for('view_records'))
    try:
        return send_from_directory(app.config['UPLOAD_FOLDER'], filename, as_attachment=True)
    except Exception as e:
        print("DOWNLOAD ERROR:", str(e))
        flash('Error downloading file: ' + str(e), 'danger')
        return redirect(url_for('view_records'))

@app.route('/manage_users', methods=['GET'])
def manage_users():
    if session.get('role') != 'admin':
        flash('Access restricted to admins.', 'danger')
        return redirect(url_for('login'))

    try:
        with sqlite3.connect('database/users.db') as conn:
            conn.execute('SELECT name FROM sqlite_master WHERE type="table" AND name="users"').fetchone()
            users = conn.execute('SELECT * FROM users').fetchall()
            print("DEBUG: Users fetched:", users)
        return render_template('manage_users.html', users=users)
    except sqlite3.OperationalError as e:
        print("MANAGE USERS DB ERROR:", str(e))
        flash(f'Error loading user data: Database error - {str(e)}', 'danger')
        return redirect(url_for('index'))
    except Exception as e:
        print("MANAGE USERS ERROR:", str(e))
        flash(f'Error loading user data: {str(e)}', 'danger')
        return redirect(url_for('index'))

@app.route('/edit_user/<int:id>', methods=['GET', 'POST'])
def edit_user(id):
    if session.get('role') != 'admin':
        flash('Access restricted to admins.', 'danger')
        return redirect(url_for('login'))

    try:
        with sqlite3.connect('database/users.db') as conn:
            if request.method == 'POST':
                name = request.form['name'].strip()
                school = request.form['school']
                department = request.form['department']
                program = request.form['program']
                contact = request.form['contact'].strip()
                email = request.form['email'].strip().lower()
                role = request.form['role']

                conn.execute('''
                    UPDATE users SET
                        name=?, school=?, department=?, program=?,
                        contact=?, email=?, role=?
                    WHERE id=?''',
                    (name, school, department, program, contact, email, role, id))
                conn.commit()
                flash('User updated successfully.', 'success')
                return redirect(url_for('manage_users'))

            user = conn.execute('SELECT * FROM users WHERE id = ?', (id,)).fetchone()
            if not user:
                flash('User not found.', 'danger')
                return redirect(url_for('manage_users'))
        return render_template('edit_profile.html', user=user)
    except sqlite3.IntegrityError:
        flash('Email already exists.', 'danger')
        return redirect(url_for('edit_user', id=id))
    except Exception as e:
        print("EDIT USER ERROR:", str(e))
        flash('Error processing user data: ' + str(e), 'danger')
        return redirect(url_for('manage_users'))

@app.route('/delete_user/<int:id>')
def delete_user(id):
    if session.get('role') != 'admin':
        flash('Access restricted to admins.', 'danger')
        return redirect(url_for('login'))

    try:
        with sqlite3.connect('database/users.db') as conn:
            conn.execute('DELETE FROM users WHERE id = ?', (id,))
            conn.commit()
        flash('User deleted successfully.', 'info')
    except Exception as e:
        print("DELETE USER ERROR:", str(e))
        flash('Error deleting user: ' + str(e), 'danger')
    return redirect(url_for('manage_users'))

# Run App
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)