.PHONY: install test demo lint clean

install:
	python -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt

test:
	pytest -q

demo:
	uvicorn app.main:app --reload

clean:
	rm -rf .venv .pytest_cache __pycache__ app/__pycache__ tests/__pycache__
