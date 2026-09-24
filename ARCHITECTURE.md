# BuildByteAcademy - Architecture & Code Overview

This document provides an in-depth look at the overall functionality, architecture, and design patterns used in the BuildByteAcademy Learning Management System (LMS).

## 1. High-Level Architecture

BuildByteAcademy is built as a monolithic web application using **Python** and the **Flask** microframework. It adheres to the MVC (Model-View-Controller) pattern, though adapted for a no-SQL, file-based persistence strategy. 

The architecture is divided into the following layers:
- **Application Factory (`app.py`)**: Initializes the Flask app, configures extensions (like CSRF and CORS), and registers all routing blueprints.
- **Controllers (`routes/`)**: Contains Flask Blueprints that handle HTTP requests, session validation, and route-specific logic. 
- **Business Logic (`services/`)**: Encapsulates the core business rules and database interactions. Routes delegate data manipulation and retrieval to these services.
- **Data Access (`services/json_database.py`)**: A custom JSON-based document database where each record is stored as a distinct JSON file to prevent concurrent write conflicts.
- **Presentation (`templates/` & `static/`)**: Jinja2 HTML templates enhanced with Tailwind CSS for modern, responsive UI design.

## 2. Core Functionality & Features

### Authentication & Authorization
- **Session Management**: Uses Flask's built-in session object (secured with HTTPOnly and Lax SameSite configurations) to maintain user state.
- **Roles**: The system supports multiple user roles:
  - **Admin**: Full access to manage courses, users, and system settings.
  - **Teacher**: Access to course creation, grading submissions, and managing content.
  - **Student**: Access to enrolled courses, procedural learning modules, and certificate viewing.
- **Two-Factor/OTP Verification**: Integrated OTP (One-Time Password) service (`services/otp_service.py`) for email-based verification during critical flows (like password resets).

### Course & Procedural Learning Engine
- **Hierarchical Content**: Courses are divided into modules, which can include various content types like Videos, Quizzes, Activities, and Handouts.
- **Procedural Learning**: The application tracks a student's progress sequentially. Students cannot jump ahead; they must complete prerequisites before unlocking subsequent modules.

### Gradebook & Assessments
- **Dynamic Grading**: Teachers can review student submissions, provide feedback, and assign grades.
- **Score Tracking**: The `grade_service.py` manages individual assessment scores and aggregates them for an overall course grade.

### Certificates
- **PDF Generation**: Upon course completion, the system automatically generates a PDF certificate (`services/certificate_service.py`).
- **Verification**: Certificates include unique IDs that can be verified externally.

## 3. Data Persistence Model

To avoid the overhead of setting up a traditional RDBMS (like PostgreSQL or MySQL) and to sidestep SQLite concurrent write locks in environments like PythonAnywhere, the system uses a custom **JSON File Database** (`services/json_database.py`).

### How It Works:
- Each "table" corresponds to a directory within the `data/` folder (e.g., `data/users/`, `data/courses/`).
- Each record corresponds to a separate `.json` file named by its UUID (e.g., `data/users/user_1234abcd.json`).
- **Atomic Writes**: Writes are performed by creating a temporary file and atomically replacing the existing file, preventing corruption during concurrent requests.
- **Indexing**: Lookups iterate through files, which is performant enough for a small-to-medium scale LMS.

## 4. Key Directories & Modules

| Directory/File | Purpose |
|----------------|---------|
| `app.py` | The main entry point and application factory. |
| `config.py` | Environment and app configuration (Keys, SMTP settings, directories). |
| `routes/` | Contains all blueprints (`auth.py`, `courses.py`, `admin_*.py`, etc.). |
| `services/` | Business logic (`auth_service.py`, `course_service.py`, `email_service.py`, etc.). |
| `utils/` | Helper functions, primarily decorators like `@login_required` and `@admin_required`. |
| `templates/` | HTML templates using Jinja2 for server-side rendering. |
| `static/` | CSS, JS, Images, and uploaded files. |
| `data/` | The runtime database directory (auto-generated). |
| `certificates/`| Storage for generated PDF certificates. |

## 5. Security Context

- **CSRF Protection**: Enabled globally via `Flask-WTF` (`CSRFProtect`). All state-changing requests require a valid CSRF token.
- **Input Validation**: Handled server-side before persisting any data to the JSON database.
- **Environment Variables**: Sensitive data (Secret Keys, SMTP passwords) are loaded via a `.env` file, keeping them out of source control. 

## 6. Future Extensibility

This codebase is modular. If the system needs to scale to a robust relational database (like PostgreSQL) in the future:
1. Simply replace `services/json_database.py` with an SQLAlchemy ORM layer.
2. Update the specific service files (e.g., `user_service.py`, `course_service.py`) to query the ORM instead of the JSON database.
3. The controllers (`routes/`) will remain entirely untouched, proving the effectiveness of the layered architecture.

## 7. Deployment (PythonAnywhere)

The application is designed to be easily deployed on **PythonAnywhere** using a Python 3.13 virtual environment.

### Deployment Steps:

1. **Clone the Repository**:
   Open a Bash console in PythonAnywhere and clone your repository.
   ```bash
   git clone <your-repository-url> mysite
   cd mysite
   ```

2. **Create a Python 3.13 Virtual Environment**:
   Create and activate a virtual environment specifically using Python 3.13.
   ```bash
   mkvirtualenv --python=/usr/bin/python3.13 venv
   # or
   python3.13 -m venv venv
   source venv/bin/activate
   ```

3. **Install Dependencies**:
   With the virtual environment activated, install the required packages:
   ```bash
   pip install -r requirements.txt
   ```

4. **Environment Configuration**:
   Create a `.env` file in the root of your project directory (`/home/buildbyteacademy/mysite/.env`) and add your production settings (ensure `SESSION_COOKIE_SECURE=True` since PythonAnywhere provides HTTPS).

5. **Web Tab Configuration**:
   - Go to the **Web** tab on the PythonAnywhere dashboard.
   - Add a new web app, choose **Manual configuration**, and select **Python 3.13**.
   - **Source code**: `/home/buildbyteacademy/mysite`
   - **Working directory**: `/home/buildbyteacademy/mysite`
   - **Virtualenv**: `/home/buildbyteacademy/mysite/venv` (or the path provided by `mkvirtualenv`)

6. **WSGI Configuration File**:
   Edit the WSGI configuration file linked in the Web tab. Replace its contents with:
   ```python
   import sys
   import os
   from dotenv import load_dotenv

   # Add your project directory to the sys.path
   project_home = '/home/buildbyteacademy/mysite'
   if project_home not in sys.path:
       sys.path = [project_home] + sys.path

   # Load environment variables from .env file
   load_dotenv(os.path.join(project_home, '.env'))

   # Import the Flask app
   from app import create_app

   # Initialize the application
   application = create_app()
   ```

7. **Database Seed (Optional)**:
   If you need to run the initial seeder, you can do so from the Bash console:
   ```bash
   cd /home/buildbyteacademy/mysite
   source venv/bin/activate
   python seed_data.py
   ```

8. **Reload the Web App**:
   Go back to the Web tab and hit the **Reload** button. Your BuildByteAcademy instance will now be live!
