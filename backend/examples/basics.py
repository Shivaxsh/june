"""Run with backend/.venv/bin/python backend/examples/basics.py."""
name = 'June'
skills = ['chat', 'transcribe', 'speak']


def describe(name, skills):
    return f'{name} has {len(skills)} skills.'


class Assistant:
    def __init__(self, name):
        self.name = name

    def greet(self):
        return f'Hello, I’m {self.name}.'


for skill in skills:
    print(skill)
print(describe(name, skills))
print(Assistant(name).greet())
