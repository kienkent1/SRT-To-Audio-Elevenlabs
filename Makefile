ENV_PATH=./conda

run:
	conda run -p $(ENV_PATH) python main.py

dev:
	conda run -p $(ENV_PATH) uvicorn main:app --reload --host 0.0.0.0 --port 8000

export:
	conda env export --prefix $(ENV_PATH) --from-history > environment.yml
	
install:
	conda env create --prefix $(ENV_PATH) -f environment.yml

update:
	conda env update --prefix $(ENV_PATH) -f environment.yml --prune