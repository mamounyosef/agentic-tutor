# ==============================================================================
# AGENTIC TUTOR - Windows Setup Script
# ==============================================================================
# This script sets up the entire Agentic Tutor platform for development on Windows
#
# Usage:
#   .\scripts\setup.ps1
#   (May need to run: Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser)
# ==============================================================================

$ErrorActionPreference = "Stop"

# ==============================================================================
# Functions
# ==============================================================================
function Print-Header {
    param([string]$Text)
    Write-Host "`n========================================" -ForegroundColor Blue
    Write-Host "$Text" -ForegroundColor Blue
    Write-Host "========================================`n" -ForegroundColor Blue
}

function Print-Success {
    param([string]$Text)
    Write-Host "✓ $Text" -ForegroundColor Green
}

function Print-Error {
    param([string]$Text)
    Write-Host "✗ $Text" -ForegroundColor Red
}

function Print-Warning {
    param([string]$Text)
    Write-Host "⚠ $Text" -ForegroundColor Yellow
}

# ==============================================================================
# STEP 1: Check prerequisites
# ==============================================================================
Print-Header "Checking Prerequisites"

# Check Python
try {
    $pythonVersion = python --version 2>&1
    Write-Host "Python version: $pythonVersion"
    Print-Success "Python found"
} catch {
    Print-Error "Python is not installed. Please install Python 3.11+ from https://www.python.org/"
    exit 1
}

# Check Node.js
try {
    $nodeVersion = node --version 2>&1
    Write-Host "Node.js version: $nodeVersion"
    Print-Success "Node.js found"
} catch {
    Print-Error "Node.js is not installed. Please install Node.js 18+ from https://nodejs.org/"
    exit 1
}

# Check MySQL
try {
    $mysqlVersion = mysql --version 2>&1
    Write-Host "MySQL: $mysqlVersion"
    Print-Success "MySQL found"
} catch {
    Print-Warning "MySQL may not be installed or not in PATH"
    Print-Warning "You can use Docker to run MySQL: docker-compose up -d constructor-db tutor-db"
}

# Check Git
try {
    $gitVersion = git --version 2>&1
    Write-Host "Git version: $gitVersion"
    Print-Success "Git found"
} catch {
    Print-Error "Git is not installed. Please install Git from https://git-scm.com/"
    exit 1
}

# ==============================================================================
# STEP 2: Create .env file
# ==============================================================================
Print-Header "Setting Up Environment"

if (-not (Test-Path .env)) {
    Print-Success "Creating .env file from .env.example"
    Copy-Item .env.example .env

    # Generate a random SECRET_KEY
    $secretKey = -join ((48..57) + (65..90) + (97..122) | Get-Random -Count 32 | % {[char]$_})
    (Get-Content .env) -replace 'your-secret-key-generate-with-openssl-here', $secretKey | Set-Content .env

    Print-Warning "Please update .env with your API keys and database credentials"
} else {
    Print-Success ".env file already exists"
}

# ==============================================================================
# STEP 3: Set up Python virtual environment
# ==============================================================================
Print-Header "Setting Up Python Virtual Environment"

Push-Location backend

if (-not (Test-Path venv)) {
    Print-Success "Creating Python virtual environment"
    python -m venv venv
}

Print-Success "Activating virtual environment"
& .\venv\Scripts\Activate.ps1

Print-Success "Installing Python dependencies"
python -m pip install --upgrade pip
pip install -e .

Pop-Location

# ==============================================================================
# STEP 4: Create necessary directories
# ==============================================================================
Print-Header "Creating Data Directories"

$directories = @(
    "backend\data\vector_db\constructor",
    "backend\data\vector_db\students",
    "backend\data\vector_db\courses",
    "backend\checkpoints\constructor",
    "backend\checkpoints\tutor",
    "backend\uploads\materials",
    "backend\logs"
)

foreach ($dir in $directories) {
    if (-not (Test-Path $dir)) {
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
    }
}

Print-Success "Data directories created"

# ==============================================================================
# STEP 5: Set up MySQL databases
# ==============================================================================
Print-Header "Setting Up MySQL Databases"

$createDb = Read-Host "Do you want to create MySQL databases now? (y/n)"
if ($createDb -eq 'y' -or $createDb -eq 'Y') {
    $mysqlPassword = Read-Host "Enter MySQL root password" -AsSecureString
    $mysqlPasswordPlain = [System.Runtime.InteropServices.Marshal]::PtrToStringAuto([System.Runtime.InteropServices.Marshal]::SecureStringToBSTR($mysqlPassword))

    Print-Success "Creating Constructor database"
    cmd /c "mysql -u root -p$mysqlPasswordPlain < backend\db\constructor\schema.sql" 2>$null

    Print-Success "Creating Tutor database"
    cmd /c "mysql -u root -p$mysqlPasswordPlain < backend\db\tutor\schema.sql" 2>$null

    Print-Success "Databases created successfully"
} else {
    Print-Warning "Skipping database creation. Run manually later:"
    Print-Warning "  mysql -u root -p < backend\db\constructor\schema.sql"
    Print-Warning "  mysql -u root -p < backend\db\tutor\schema.sql"
}

# ==============================================================================
# STEP 6: Set up frontend
# ==============================================================================
Print-Header "Setting Up Frontend"

Push-Location frontend

Print-Success "Installing Node.js dependencies"
npm install

Pop-Location

# ==============================================================================
# STEP 7: Summary
# ==============================================================================
Print-Header "Setup Complete!"

Write-Host "The Agentic Tutor platform is ready for development.`n" -ForegroundColor Green

Write-Host "To start the development servers:"
Write-Host ""
Write-Host "Backend:" -ForegroundColor Blue
Write-Host "  cd backend"
Write-Host "  .\venv\Scripts\Activate.ps1"
Write-Host "  uvicorn app.main:app --reload"
Write-Host ""
Write-Host "Frontend:" -ForegroundColor Blue
Write-Host "  cd frontend"
Write-Host "  npm run dev"
Write-Host ""
Write-Host "Remember to update your .env file with:" -ForegroundColor Yellow
Write-Host "  - Database connection strings"
Write-Host "  - Z.AI API key (or your LLM provider)"
Write-Host "  - JWT secret key (auto-generated)"
Write-Host ""
Write-Host "For Docker deployment:" -ForegroundColor Blue
Write-Host "  docker-compose up -d"
Write-Host ""

Print-Success "Happy coding!"
