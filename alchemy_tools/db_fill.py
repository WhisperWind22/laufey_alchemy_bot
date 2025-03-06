import pandas as pd
import sqlite3
DB_PATH = "alchemy.db"
MATERIAL_TYPES = ["Магические Металлы","Магические Компоненты","Травы"]

def fill_ingredients_table(young_alchemy_data):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    old_cols = young_alchemy_data.columns
    rename_map = {}
    _new_cols = ["title","material_analog","main_effect","side_effect","identifier"]
    for old_col,new_col in zip(old_cols,_new_cols):
        rename_map[old_col] = new_col

    young_alchemy_data.rename(columns=rename_map,inplace=True)
    current_material_type = None
    current_ingredient = None
    current_ingredient_id = None
    for index,row in young_alchemy_data.iterrows():
        if isinstance(row["material_analog"],str):
            material_analog = row["material_analog"].strip()
            if any(t in material_analog for t in MATERIAL_TYPES):
                current_material_type = material_analog
                # young_alchemy_data.at[index,"material_analog"] = None
        if isinstance(row["title"],str):
            current_ingredient = row["title"].strip()
            main_effect = row["main_effect"].strip()
            side_effect = row["side_effect"].strip()
            identifier = row["identifier"].strip()
            material_analog = row["material_analog"].strip()
            ingredient_order = 1

            cursor.execute("""
                SELECT id FROM ingredients WHERE code = ?
                """,(identifier,))
            current_ingredient_id = cursor.fetchone()
            if current_ingredient_id:
                current_ingredient_id = current_ingredient_id[0]
                current_ingredient=None
            else:
                cursor.execute("""
                    INSERT INTO ingredients (code,material_analog,ingredient_type,name) VALUES (?,?,?,?)
                    """,(identifier,material_analog,current_material_type,current_ingredient))
                conn.commit()
                current_ingredient_id = cursor.lastrowid

                cursor.execute("""
                    SELECT id FROM effects WHERE description = ?
                    """,(main_effect.lower(),))
                main_effect_id = cursor.fetchone()
                if main_effect_id:
                    main_effect_id = main_effect_id[0]
                else:
                    cursor.execute("""
                        INSERT INTO effects (description) VALUES (?)
                        """,(main_effect.lower(),))
                    conn.commit()
                    main_effect_id = cursor.lastrowid
                
                cursor.execute("""
                    SELECT id FROM effects WHERE description = ?
                    """,(side_effect.lower(),))
                side_effect_id = cursor.fetchone()
                if side_effect_id:
                    side_effect_id = side_effect_id[0]
                else:
                    cursor.execute("""
                        INSERT INTO effects (description) VALUES (?)
                        """,(side_effect.lower(),))
                    conn.commit()
                    side_effect_id = cursor.lastrowid
                
                cursor.execute("""
                    INSERT INTO properties (ingredient_id,effect_id,ingredient_order,is_main) VALUES (?,?,?,?)
                    """,(current_ingredient_id,main_effect_id,0,True))
                conn.commit()
                
                cursor.execute("""
                    INSERT INTO properties (ingredient_id,effect_id,ingredient_order,is_main) VALUES (?,?,?,?)
                    """,(current_ingredient_id,side_effect_id,1,False))
                conn.commit()
        elif isinstance(row["side_effect"],str):
            side_effect = row["side_effect"].strip()
            ingredient_order = ingredient_order+1
            cursor.execute("""
                SELECT id FROM effects WHERE description = ?
                """,(side_effect.lower(),))
            side_effect_id = cursor.fetchone()
            if side_effect_id:
                side_effect_id = side_effect_id[0]
            else:
                cursor.execute("""
                    INSERT INTO effects (description) VALUES (?)
                    """,(side_effect.lower(),))
                conn.commit()
                side_effect_id = cursor.lastrowid
                
            cursor.execute("""
                INSERT INTO properties (ingredient_id,effect_id,ingredient_order,is_main) VALUES (?,?,?,?)
                """,(current_ingredient_id,side_effect_id,ingredient_order,False))
            conn.commit()
    conn.close()

def main():
    young_alchemy_data = pd.read_csv("young_alchemy.csv")
    fill_ingredients_table(young_alchemy_data)

if __name__ == "__main__":
    main()
