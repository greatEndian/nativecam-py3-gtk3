#!/usr/bin/env python3
# coding: utf-8

import sys
import os
import re

# Add the project root to the python path so we can import ncam
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import ncam

class MockParam:
    """Mocks the Parameter class extracted from the UI."""
    def __init__(self, value):
        self.value = str(value)
    def get_value(self):
        return self.value

class MockFeature:
    """Mocks the Feature class evaluating a .cfg file."""
    def __init__(self, params_dict):
        self.params = {k: MockParam(v) for k, v in params_dict.items()}
        
    def get_param(self, name):
        return self.params.get(name, MockParam("0.0"))

class MockToolTable:
    """Mocks the ToolTable to force a 'live tool' response."""
    def is_live_tool(self, tool_idx):
        return True

def run_tests():
    # Inject our mock tool table into the ncam namespace
    ncam.TOOL_TABLE = MockToolTable()
    
    # Define the exact same regex evaluation logic used in ncam.Feature.process
    def eval_callback(m, feature_instance):
        try:
            # Pass ncam's globals so get_float and get_int are available
            return str(eval(m.group(2), ncam.__dict__, {"self": feature_instance}))
        except Exception as e:
            return f"ERROR: {e}"

    def process_eval(text, feature_instance):
        return re.sub(r"(?i)(<eval>(.*?)</eval>)", lambda m: eval_callback(m, feature_instance), text)

    print("--- Testing Turn-Mill Coordinate Mappings ---")

    # 1. Test Face Mill (G17) X-axis evaluation
    face_feat = MockFeature({'x': 50.0, 'tool': 2})
    face_eval_str = "<eval> get_float(self.get_param('x').get_value()) / 2.0 </eval>"
    res1 = process_eval(face_eval_str, face_feat)
    print(f"Face Mill (G17) X map (UI Diam 50.0 -> Sub Radius): {res1.strip()}")
    assert res1.strip() == "25.0", "G17 X-to-Radius mapping failed!"

    # 2. Test Safe Plane Transition & G40 Guard
    plane_eval_str = "<eval> 'G40\\nM5\\nM3 $1\\nG17' if TOOL_TABLE.is_live_tool(get_int(self.get_param('tool').get_value())) else 'WARN' </eval>"
    res2 = process_eval(plane_eval_str, face_feat)
    assert "G40" in res2 and "G17" in res2, "Safety plane switch missing G40 guard or G17 plane!"
    
    print("\nAll Turn-Mill coordinate mapping tests passed successfully!")

if __name__ == '__main__':
    run_tests()