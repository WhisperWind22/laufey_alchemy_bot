from alchemy_tools.db_setup import setup_database
from alchemy_tools.db_fill import fill_ingredients_table_v4, user_testing_add_all_ingredients
import os
import logging
logging.basicConfig(level=logging.INFO)
DB_PATH = "alchemy.db"

def main():
    if os.path.exists(DB_PATH):
        logging.info("DB deleted")
        os.remove(DB_PATH)
    setup_database()
    fill_ingredients_table_v4()
    user_testing_add_all_ingredients()

if __name__ == "__main__":
    main()
