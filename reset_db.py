from alchemy_tools.db_setup import setup_database,add_effects_to_db
from alchemy_tools.db_fill import fill_ingredients_table,user_testing_add_all_ingredients
import pandas as pd
import os
import logging
logging.basicConfig(level=logging.INFO)
DB_PATH = "alchemy.db"

def main():
    if os.path.exists(DB_PATH):
        logging.info("DB deleted")
        os.remove(DB_PATH)
    setup_database()
    effects_df = pd.read_pickle("all_effects_df.pkl")
    add_effects_to_db(effects_df)

    young_alchemy_data = pd.read_csv("young_alchemy.csv")
    fill_ingredients_table(young_alchemy_data)
    user_testing_add_all_ingredients()

if __name__ == "__main__":
    main()
