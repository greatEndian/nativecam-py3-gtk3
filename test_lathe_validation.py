#!/usr/bin/env python3
# coding: utf-8

import os
import re

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
CFG_DIR = os.path.join(PROJECT_ROOT, 'cfg', 'lathe')
LIB_LATHE = os.path.join(PROJECT_ROOT, 'lib', 'lathe')
LIB_MILL = os.path.join(PROJECT_ROOT, 'lib', 'mill')
LIB_UTIL = os.path.join(PROJECT_ROOT, 'lib', 'utilities')

def count_args(args_str):
    count = 0
    depth = 0
    for char in args_str:
        if char == '[':
            if depth == 0:
                count += 1
            depth += 1
        elif char == ']':
            depth -= 1
    return count

def parse_sig_comment(line):
    # Remove surrounding comments characters
    clean = line.strip()
    if clean.startswith(';'):
        clean = clean[1:].strip()
    if clean.startswith('(') and clean.endswith(')'):
        clean = clean[1:-1].strip()
    if clean.lower().startswith('call'):
        clean = clean[4:].strip()
    if clean.startswith(':'):
        clean = clean[1:].strip()
    
    if '[' in clean:
        return count_args(clean), clean
    else:
        words = [w for w in clean.split() if w]
        return len(words), clean

def find_subroutine_file(subname):
    # Check lathe, mill, and utilities
    for folder in [LIB_LATHE, LIB_MILL, LIB_UTIL]:
        path = os.path.join(folder, f"{subname}.ngc")
        if os.path.exists(path):
            return path
    return None

def analyze_cfg_file(filepath):
    filename = os.path.basename(filepath)
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    # Find subroutine calls, e.g. o<subname> call [args...] or o<subname> CALL [args...]
    # Using regex that captures o<name> call or o<name> CALL
    calls = re.findall(r'(?i)o<(\w+)>\s+(?:call|CALL)\s*(.*)', content)
    
    results = []
    for subname, args_str in calls:
        arg_count = count_args(args_str)
        sub_file = find_subroutine_file(subname)
        
        status = "OK"
        expected_count = None
        sig_str = "Unknown"
        detail = ""
        
        if not sub_file:
            status = "MISSING_SUB"
            detail = f"Subroutine file '{subname}.ngc' not found in any library path."
        else:
            # Parse signature comment
            with open(sub_file, 'r', encoding='utf-8') as sf:
                lines = sf.readlines()
            
            sig_lines = []
            for i, line in enumerate(lines[:10]):
                if 'call' in line.lower() and '(' in line:
                    sig_lines.append(line)
                    # Check next lines for continuation comment
                    for next_line in lines[i+1:i+5]:
                        nl_strip = next_line.strip()
                        if nl_strip.startswith('(') and ('[' in nl_strip or '...' in nl_strip or 'args' in nl_strip or 'ptr' in nl_strip):
                            sig_lines.append(next_line)
                        else:
                            break
                    break
            
            sig_line = " ".join(sig_lines) if sig_lines else None
            
            if sig_line:
                expected_count, sig_str = parse_sig_comment(sig_line)
                if expected_count != arg_count:
                    status = "MISMATCH"
                    detail = f"Passed {arg_count} args, but subroutine signature expects {expected_count}."
            else:
                status = "NO_SIGNATURE"
                detail = f"Could not find a (CALL ...) signature comment in {os.path.basename(sub_file)}."
        
        results.append({
            'subname': subname,
            'passed_args': arg_count,
            'expected_args': expected_count,
            'status': status,
            'detail': detail,
            'sig_str': sig_str
        })
    
    return results

def run_verification():
    print("====================================================")
    print("     NATIVECAM LATHE CYCLE VERIFICATION SUITE")
    print("====================================================")
    
    if not os.path.exists(CFG_DIR):
        print(f"Error: Lathe config directory not found at {CFG_DIR}")
        return
        
    cfg_files = sorted([f for f in os.listdir(CFG_DIR) if f.endswith('.cfg')])
    
    total_calls = 0
    total_warnings = 0
    
    for filename in cfg_files:
        filepath = os.path.join(CFG_DIR, filename)
        calls = analyze_cfg_file(filepath)
        if not calls:
            continue
            
        print(f"\n📁 File: cfg/lathe/{filename}")
        for res in calls:
            total_calls += 1
            if res['status'] == "OK":
                print(f"  🟢 o<{res['subname']}> CALL: Passed {res['passed_args']} args [OK]")
            elif res['status'] == "MISMATCH":
                total_warnings += 1
                print(f"  ❌ o<{res['subname']}> CALL: Passed {res['passed_args']} args, Expected {res['expected_args']} [MISMATCH]")
                print(f"     ↳ Signature: {res['sig_str']}")
                print(f"     ↳ Reason: {res['detail']}")
            elif res['status'] == "MISSING_SUB":
                total_warnings += 1
                print(f"  ❌ o<{res['subname']}> CALL: Passed {res['passed_args']} args [MISSING SUBROUTINE]")
                print(f"     ↳ Reason: {res['detail']}")
            else:
                print(f"  🟡 o<{res['subname']}> CALL: Passed {res['passed_args']} args [NO SIGNATURE]")
                if res['detail']:
                    print(f"     ↳ Detail: {res['detail']}")
                    
    print("\n====================================================")
    print(f"Verification completed. Checked {total_calls} subroutine calls.")
    if total_warnings > 0:
        print(f"⚠️  Found {total_warnings} errors/mismatches.")
    else:
        print("🎉 All scanned lathe subroutine calls match their signatures!")
    print("====================================================")

if __name__ == '__main__':
    run_verification()
