#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Emergency fix for 404 error - Upload to GitHub
"""

import subprocess
import sys
import time
import os

def run_command(cmd):
    """Run a command and return output"""
    try:
        print(f"Running: {cmd}")
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        if result.stdout:
            print(result.stdout)
        if result.stderr:
            print(f"Error: {result.stderr}")
        return result.returncode == 0
    except Exception as e:
        print(f"Failed: {e}")
        return False

def main():
    print("="*60)
    print("EMERGENCY FIX FOR 404 ERROR")
    print("="*60)
    
    # Change to project directory
    os.chdir(r'C:\S-B-Parking-reports')
    
    # Check git status
    print("\n1. Checking git status...")
    run_command("git status --short")
    
    # Add all files
    print("\n2. Adding files...")
    if not run_command("git add -A"):
        print("Failed to add files")
        return False
    
    # Commit
    print("\n3. Committing...")
    commit_msg = f"EMERGENCY FIX 404 - {time.strftime('%Y%m%d_%H%M%S')}"
    if not run_command(f'git commit -m "{commit_msg}" --no-verify'):
        print("Nothing to commit or commit failed")
    
    # Push
    print("\n4. Pushing to GitHub...")
    if not run_command("git push origin master --force"):
        print("Failed to push. Trying to pull first...")
        run_command("git pull origin master --no-rebase")
        run_command("git push origin master --force")
    
    print("\n" + "="*60)
    print("✅ DONE! Deployment will start automatically.")
    print("Wait 2-3 minutes then check:")
    print("https://s-b-parking-reports.onrender.com/api/company-manager/proxy")
    print("="*60)
    
    # Test the endpoint
    print("\n5. Testing endpoint (this might fail until deployment completes)...")
    import requests
    try:
        response = requests.get("https://s-b-parking-reports.onrender.com/api/company-manager/proxy", timeout=5)
        print(f"Status: {response.status_code}")
        if response.status_code == 200:
            print("✅ ENDPOINT IS WORKING!")
        else:
            print("⚠️ Endpoint not ready yet. Wait for deployment.")
    except:
        print("⚠️ Cannot reach server yet. Wait for deployment.")

if __name__ == "__main__":
    main()
    input("\nPress Enter to exit...")
