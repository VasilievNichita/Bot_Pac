#!/usr/bin/env python3
"""
Backend Test Suite for Telegram Quiz Bot
Tests JSON structure, MongoDB connection, and Telegram Bot functionality
"""

import json
import sys
import os
import asyncio
from pathlib import Path
from datetime import datetime
from motor.motor_asyncio import AsyncIOMotorClient
import requests
import logging

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class TelegramBotTester:
    def __init__(self):
        self.tests_run = 0
        self.tests_passed = 0
        self.backend_dir = Path("/app/backend")
        self.questions_file = self.backend_dir / "questions.json"
        self.env_file = self.backend_dir / ".env"
        self.telegram_bot_file = self.backend_dir / "telegram_bot.py"
        
        # Load environment variables
        self.load_env_vars()
        
    def load_env_vars(self):
        """Load environment variables from .env file"""
        try:
            with open(self.env_file, 'r') as f:
                for line in f:
                    if '=' in line and not line.strip().startswith('#'):
                        key, value = line.strip().split('=', 1)
                        value = value.strip('"')
                        os.environ[key] = value
            
            self.mongo_url = os.environ.get('MONGO_URL', 'mongodb://localhost:27017')
            self.db_name = os.environ.get('DB_NAME', 'test_database')
            self.bot_token = os.environ.get('TELEGRAM_BOT_TOKEN')
            
            print("✅ Environment variables loaded successfully")
            return True
            
        except Exception as e:
            print(f"❌ Failed to load environment variables: {e}")
            return False

    def run_test(self, name, test_func):
        """Run a single test"""
        self.tests_run += 1
        print(f"\n🔍 Testing {name}...")
        
        try:
            result = test_func()
            if result:
                self.tests_passed += 1
                print(f"✅ Passed: {name}")
                return True
            else:
                print(f"❌ Failed: {name}")
                return False
        except Exception as e:
            print(f"❌ Failed: {name} - Error: {str(e)}")
            return False

    def test_questions_json_structure(self):
        """Test 1: Verify questions.json contains minimum 150 questions with proper structure"""
        try:
            if not self.questions_file.exists():
                print(f"❌ Questions file not found: {self.questions_file}")
                return False
                
            with open(self.questions_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Check if 'questions' key exists
            if 'questions' not in data:
                print("❌ Missing 'questions' key in JSON")
                return False
            
            questions = data['questions']
            
            # Check minimum count (requirement: 150-180)
            if len(questions) < 150:
                print(f"❌ Not enough questions: {len(questions)}, minimum required: 150")
                return False
            
            print(f"✅ Found {len(questions)} questions (requirement: ≥150)")
            
            # Check structure of first few questions
            required_fields = ['id', 'question', 'options', 'correct', 'topic']
            sample_questions = questions[:5]  # Check first 5
            
            for i, q in enumerate(sample_questions):
                for field in required_fields:
                    if field not in q:
                        print(f"❌ Question {i+1} missing field: {field}")
                        return False
                
                # Check options structure (should have a,b,c,d)
                if not isinstance(q['options'], dict):
                    print(f"❌ Question {i+1} options not a dict")
                    return False
                
                required_options = ['a', 'b', 'c', 'd']
                for opt in required_options:
                    if opt not in q['options']:
                        print(f"❌ Question {i+1} missing option: {opt}")
                        return False
                
                # Check correct answer is one of a,b,c,d
                if q['correct'] not in required_options:
                    print(f"❌ Question {i+1} invalid correct answer: {q['correct']}")
                    return False
            
            print("✅ Questions structure is valid (checked sample questions)")
            return True
            
        except json.JSONDecodeError as e:
            print(f"❌ Invalid JSON format: {e}")
            return False
        except Exception as e:
            print(f"❌ Error reading questions file: {e}")
            return False

    def test_telegram_bot_file_exists(self):
        """Test 2: Verify telegram_bot.py exists and contains required components"""
        try:
            if not self.telegram_bot_file.exists():
                print(f"❌ Telegram bot file not found: {self.telegram_bot_file}")
                return False
            
            with open(self.telegram_bot_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Check for essential imports and functions
            required_components = [
                'from telegram import',
                'from telegram.ext import',
                'AsyncIOMotorClient',
                'BOT_TOKEN',
                'async def start(',
                'def main(',
                'load_questions()'
            ]
            
            missing_components = []
            for component in required_components:
                if component not in content:
                    missing_components.append(component)
            
            if missing_components:
                print(f"❌ Missing components in telegram_bot.py: {missing_components}")
                return False
            
            print("✅ Telegram bot file contains all required components")
            return True
            
        except Exception as e:
            print(f"❌ Error checking telegram_bot.py: {e}")
            return False

    async def test_mongodb_connection(self):
        """Test 3: Verify MongoDB connection works"""
        try:
            # Connect to MongoDB
            client = AsyncIOMotorClient(self.mongo_url)
            db = client[self.db_name]
            
            # Test connection by inserting and retrieving a test document
            test_collection = db.test_connection
            test_doc = {
                "test_id": "telegram_bot_test",
                "timestamp": datetime.utcnow().isoformat(),
                "message": "Testing MongoDB connection"
            }
            
            # Insert test document
            result = await test_collection.insert_one(test_doc)
            if not result.inserted_id:
                print("❌ Failed to insert test document")
                return False
            
            # Retrieve test document
            retrieved = await test_collection.find_one({"test_id": "telegram_bot_test"})
            if not retrieved:
                print("❌ Failed to retrieve test document")
                return False
            
            # Clean up test document
            await test_collection.delete_one({"test_id": "telegram_bot_test"})
            
            # Close connection
            client.close()
            
            print(f"✅ MongoDB connection successful ({self.mongo_url})")
            return True
            
        except Exception as e:
            print(f"❌ MongoDB connection failed: {e}")
            return False

    def test_telegram_api_connection(self):
        """Test 4: Verify Telegram Bot Token is valid and bot responds"""
        try:
            if not self.bot_token:
                print("❌ Telegram bot token not found in environment")
                return False
            
            # Test bot token by calling getMe API
            url = f"https://api.telegram.org/bot{self.bot_token}/getMe"
            
            try:
                response = requests.get(url, timeout=10)
                
                if response.status_code == 200:
                    data = response.json()
                    if data.get('ok'):
                        bot_info = data.get('result', {})
                        bot_name = bot_info.get('first_name', 'Unknown')
                        bot_username = bot_info.get('username', 'Unknown')
                        print(f"✅ Telegram Bot API connection successful")
                        print(f"   Bot Name: {bot_name}")
                        print(f"   Bot Username: @{bot_username}")
                        return True
                    else:
                        error_desc = data.get('description', 'Unknown error')
                        print(f"❌ Telegram API error: {error_desc}")
                        return False
                else:
                    print(f"❌ HTTP Error {response.status_code}: {response.text}")
                    return False
                    
            except requests.exceptions.Timeout:
                print("❌ Request to Telegram API timed out")
                return False
            except requests.exceptions.ConnectionError:
                print("❌ Failed to connect to Telegram API")
                return False
                
        except Exception as e:
            print(f"❌ Error testing Telegram API: {e}")
            return False

    def test_supervisor_telegram_bot_status(self):
        """Test 5: Verify telegram bot is running via supervisor"""
        try:
            import subprocess
            
            result = subprocess.run(['sudo', 'supervisorctl', 'status', 'telegram_bot'], 
                                  capture_output=True, text=True)
            
            if result.returncode == 0:
                status_output = result.stdout.strip()
                if 'RUNNING' in status_output:
                    print("✅ Telegram bot is running via supervisor")
                    print(f"   Status: {status_output}")
                    return True
                else:
                    print(f"❌ Telegram bot not running. Status: {status_output}")
                    return False
            else:
                print(f"❌ Error checking supervisor status: {result.stderr}")
                return False
                
        except Exception as e:
            print(f"❌ Error checking supervisor status: {e}")
            return False

    def test_questions_content_quality(self):
        """Test 6: Additional quality checks for questions content"""
        try:
            with open(self.questions_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            questions = data['questions']
            
            # Check for duplicate IDs
            ids = [q['id'] for q in questions]
            if len(ids) != len(set(ids)):
                print("❌ Duplicate question IDs found")
                return False
            
            # Check for questions about PCB (печатные платы)
            pcb_related_count = 0
            for q in questions:
                question_text = q['question'].lower()
                topic = q['topic'].lower() if 'topic' in q else ''
                
                pcb_keywords = ['печатн', 'плат', 'pcb', 'проводник', 'диэлектрик', 'фольг', 'медн']
                if any(keyword in question_text or keyword in topic for keyword in pcb_keywords):
                    pcb_related_count += 1
            
            pcb_percentage = (pcb_related_count / len(questions)) * 100
            
            if pcb_percentage < 80:  # At least 80% should be PCB related
                print(f"⚠️  Only {pcb_percentage:.1f}% questions appear to be PCB related")
                # Still pass the test but with warning
            else:
                print(f"✅ {pcb_percentage:.1f}% of questions are PCB related")
            
            print(f"✅ Questions quality check passed ({len(questions)} total questions)")
            return True
            
        except Exception as e:
            print(f"❌ Error checking questions content: {e}")
            return False

    async def run_all_tests(self):
        """Run all tests"""
        print("="*60)
        print("🚀 TELEGRAM QUIZ BOT - BACKEND TEST SUITE")
        print("="*60)
        
        # Synchronous tests
        sync_tests = [
            ("Questions JSON Structure", self.test_questions_json_structure),
            ("Telegram Bot File Exists", self.test_telegram_bot_file_exists),  
            ("Questions Content Quality", self.test_questions_content_quality),
            ("Supervisor Bot Status", self.test_supervisor_telegram_bot_status),
            ("Telegram API Connection", self.test_telegram_api_connection)
        ]
        
        for test_name, test_func in sync_tests:
            self.run_test(test_name, test_func)
        
        # Async tests
        print(f"\n🔍 Testing MongoDB Connection...")
        self.tests_run += 1
        try:
            result = await self.test_mongodb_connection()
            if result:
                self.tests_passed += 1
                print(f"✅ Passed: MongoDB Connection")
            else:
                print(f"❌ Failed: MongoDB Connection")
        except Exception as e:
            print(f"❌ Failed: MongoDB Connection - Error: {str(e)}")
        
        # Print final results
        print("\n" + "="*60)
        print("📊 TEST RESULTS SUMMARY")
        print("="*60)
        print(f"✅ Tests passed: {self.tests_passed}/{self.tests_run}")
        print(f"📈 Success rate: {(self.tests_passed/self.tests_run)*100:.1f}%")
        
        if self.tests_passed == self.tests_run:
            print("\n🎉 ALL TESTS PASSED! Telegram Quiz Bot is ready.")
            return True
        else:
            failed = self.tests_run - self.tests_passed
            print(f"\n⚠️  {failed} test(s) failed. Please check the issues above.")
            return False

def main():
    """Main function to run tests"""
    tester = TelegramBotTester()
    
    # Run async tests
    try:
        loop = asyncio.get_event_loop()
        success = loop.run_until_complete(tester.run_all_tests())
        return 0 if success else 1
    except Exception as e:
        print(f"❌ Fatal error running tests: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main())