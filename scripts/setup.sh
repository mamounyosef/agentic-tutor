#!/bin/bash
# ==============================================================================
# AGENTIC TUTOR - Setup Script
# ==============================================================================
# This script sets up the entire Agentic Tutor platform for development
#
# Usage:
#   chmod +x scripts/setup.sh
#   ./scripts/setup.sh
# ==============================================================================

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Print functions
print_header() {
    echo -e "\n${BLUE}========================================${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}========================================${NC}\n"
}

print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

print_error() {
    echo -e "${RED}✗ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠ $1${NC}"
}

# ==============================================================================
# STEP 1: Check prerequisites
# ==============================================================================
print_header "Checking Prerequisites"

# Check if Python 3.11+ is installed
if ! command -v python3 &> /dev/null; then
    print_error "Python 3 is not installed"
    exit 1
fi

PYTHON_VERSION=$(python3 --version | cut -d' ' -f2 | cut -d'.' -f1,2)
print_success "Python $PYTHON_VERSION found"

# Check if Node.js 18+ is installed
if ! command -v node &> /dev/null; then
    print_error "Node.js is not installed"
    exit 1
fi

NODE_VERSION=$(node --version)
print_success "Node.js $NODE_VERSION found"

# Check if MySQL is installed
if ! command -v mysql &> /dev/null; then
    print_warning "MySQL is not installed. Please install MySQL 8.0+"
    print_warning "You can use Docker to run MySQL: docker-compose up -d constructor-db tutor-db"
fi

# Check if Git is installed
if ! command -v git &> /dev/null; then
    print_error "Git is not installed"
    exit 1
fi
print_success "Git found"

# ==============================================================================
# STEP 2: Create .env file
# ==============================================================================
print_header "Setting Up Environment"

if [ ! -f .env ]; then
    print_success "Creating .env file from .env.example"
    cp .env.example .env

    # Generate a random SECRET_KEY
    SECRET_KEY=$(openssl rand -hex 32)
    sed -i "s/your-secret-key-generate-with-openssl-here/$SECRET_KEY/" .env

    print_warning "Please update .env with your API keys and database credentials"
else
    print_success ".env file already exists"
fi

# ==============================================================================
# STEP 3: Set up Python virtual environment
# ==============================================================================
print_header "Setting Up Python Virtual Environment"

cd backend

if [ ! -d "venv" ]; then
    print_success "Creating Python virtual environment"
    python3 -m venv venv
fi

print_success "Activating virtual environment"
source venv/bin/activate

print_success "Installing Python dependencies"
pip install --upgrade pip
pip install -e .

cd ..

# ==============================================================================
# STEP 4: Create necessary directories
# ==============================================================================
print_header "Creating Data Directories"

mkdir -p backend/data/vector_db/constructor
mkdir -p backend/data/vector_db/students
mkdir -p backend/data/vector_db/courses
mkdir -p backend/checkpoints/constructor
mkdir -p backend/checkpoints/tutor
mkdir -p backend/uploads/materials
mkdir -p backend/logs

print_success "Data directories created"

# ==============================================================================
# STEP 5: Set up MySQL databases
# ==============================================================================
print_header "Setting Up MySQL Databases"

read -p "Do you want to create MySQL databases now? (y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    read -p "Enter MySQL root password: " -s MYSQL_ROOT_PASSWORD
    echo

    print_success "Creating Constructor database"
    mysql -u root -p"$MYSQL_ROOT_PASSWORD" < backend/db/constructor/schema.sql

    print_success "Creating Tutor database"
    mysql -u root -p"$MYSQL_ROOT_PASSWORD" < backend/db/tutor/schema.sql

    print_success "Databases created successfully"
else
    print_warning "Skipping database creation. Run manually later:"
    print_warning "  mysql -u root -p < backend/db/constructor/schema.sql"
    print_warning "  mysql -u root -p < backend/db/tutor/schema.sql"
fi

# ==============================================================================
# STEP 6: Set up frontend
# ==============================================================================
print_header "Setting Up Frontend"

cd frontend

print_success "Installing Node.js dependencies"
npm install

cd ..

# ==============================================================================
# STEP 7: Summary
# ==============================================================================
print_header "Setup Complete!"

echo -e "${GREEN}The Agentic Tutor platform is ready for development.${NC}\n"

echo "To start the development servers:"
echo ""
echo -e "${BLUE}Backend:${NC}"
echo "  cd backend"
echo "  source venv/bin/activate"
echo "  uvicorn app.main:app --reload"
echo ""
echo -e "${BLUE}Frontend:${NC}"
echo "  cd frontend"
echo "  npm run dev"
echo ""
echo -e "${YELLOW}Remember to update your .env file with:${NC}"
echo "  - Database connection strings"
echo "  - Z.AI API key (or your LLM provider)"
echo "  - JWT secret key (auto-generated)"
echo ""
echo -e "${BLUE}For Docker deployment:${NC}"
echo "  docker-compose up -d"
echo ""
print_success "Happy coding!"
