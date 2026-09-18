import py_compile
py_compile.compile('backend/services/db.py', doraise=True)
print("SYNTAX OK")
