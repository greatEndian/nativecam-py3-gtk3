#!/usr/bin/env python3
# coding: utf-8

import sys
import os
import math

# Add the project root to the python path so we can import ncam
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import ncam

class MockVKB:
    """
    A mock class that attaches the real `compute` method from ncam.py
    so we can test the math parser without initializing GTK window elements.
    """
    compute = ncam.VKB.compute

def run_tests():
    vkb = MockVKB()
    
    test_cases = [
        ("5+5", True, 10.0),
        ("10-3", True, 7.0),
        ("2*3", True, 6.0),
        ("10/2", True, 5.0),
        ("(10+5)/2", True, 7.5),
        ("2*(3+4)", True, 14.0),
        ("2*(3+4", True, 14.0),  # Tests auto-closing parentheses
        ("Pi", True, math.pi),
        ("2*Pi", True, 2 * math.pi),
        ("invalid", False, 0.0), # Tests exception handling on malformed input
        ("5/0", False, 0.0),     # ZeroDivisionError correctly caught
    ]
    
    all_passed = True
    for expr, expected_success, expected_val in test_cases:
        success, val = vkb.compute(expr)
        if success != expected_success:
            print(f"FAIL: '{expr}' -> expected success {expected_success}, got {success}")
            all_passed = False
        elif success and abs(val - expected_val) > 1e-9:
            print(f"FAIL: '{expr}' -> expected {expected_val}, got {val}")
            all_passed = False
        else:
            print(f"PASS: '{expr}' -> {val if success else '(expected error)'}")
            
    if all_passed:
        print("\nAll VKB math parsing tests passed successfully!")
        sys.exit(0)
    else:
        print("\nSome tests failed.")
        sys.exit(1)

if __name__ == '__main__':
    run_tests()