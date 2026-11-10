convert:
	python src/convert.py input.txt output.pdf

app:
	python -m src.app

client:
	python -m src.client

test:
	echo "Running pytest with coverage..."
	coverage run -m pytest tests/
	coverage report -m

clear-files:
	rm -f input/*.txt output/*.pdf
