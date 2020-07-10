"""
utils.py

   utilities

@author: K.Edeline
"""


def remove_suffix(s, suffix):
    if s.endswith(suffix):
        s = s[:-len(suffix)]
    return s
    

