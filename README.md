# BuildByteAcademy - Learning Management System (LMS)

A complete, production-ready Learning Management System built with Python Flask.

*Note: The webapp name is **BuildByteAcademy**. It is currently configured for local development but will be deployed on **PythonAnywhere**.*

## Features

* **Dual Portals:** Separate interfaces for Students and Administrators.
* **Course Management:** Create courses with videos, quizzes, activities, and handouts.
* **Procedural Learning:** Track student progress step-by-step through course materials.
* **Gradebook:** Dynamic grading system with individual assessment scoring.
* **Certificates:** Automatically generated PDF certificates upon course completion.
* **Authentication:** Secure session-based authentication with OTP email verification.
* **Data Persistence:** File-based JSON database architecture ensuring no concurrent write conflicts.
* **Modern UI/UX:** Clean, responsive design using Tailwind CSS and Phosphor Icons.

## Setup Instructions

### 1. Requirements

* Python 3.9+
* Recommended: Virtual Environment

### 2. Installation

Clone the repository and install the dependencies:

```bash
# Create and activate virtual environment
python -m venv venv
venv\Scripts\activate  # Windows
source venv/bin/activate  # macOS/Linux

# Install dependencies
pip install -r requirements.txt
```

### 3. Configuration

A `.env` file handles configuration. Ensure it contains the following:

```env
SECRET_KEY=your_super_secret_key_here
SESSION_COOKIE_HTTPONLY=True
SESSION_COOKIE_SECURE=False  # Set to True in production (requires HTTPS)

# SMTP Settings for Email OTP
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_EMAIL=your_email@gmail.com
SMTP_APP_PASSWORD=your_app_password
```

### 4. Database Initialization

Run the seed script to populate the initial database structures, create an admin account, and a test student:

```bash
python seed_data.py
```

**Default Accounts:**
* **Admin:** `admin@lms.com` / `Admin123!`
* **Student:** `student@lms.com` / `Student123!`

### 5. Running the Application

```bash
python app.py
```

The application will be available at `http://127.0.0.1:5000/`.

## Architecture

The project uses a clean, modular architecture:

* `app.py`: Application factory and entry point.
* `config.py`: Environment configuration.
* `routes/`: Flask blueprints handling web requests (Controllers).
* `services/`: Business logic and database interactions.
* `utils/`: Helper functions and decorators.
* `templates/`: Jinja2 HTML templates styled with Tailwind CSS.
* `data/`: JSON files acting as the database (created automatically).

## Security Measures

* **Password Hashing:** Passwords are hashed using Werkzeug security.
* **CSRF Protection:** Enabled via `Flask-WTF` on all forms.
* **Session Security:** Enforced HTTPOnly cookies.
* **Access Control:** Route protection using `@login_required` and `@admin_required` decorators.
