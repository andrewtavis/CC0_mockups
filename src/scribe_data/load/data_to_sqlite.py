"""
Converts all or desired JSON data generated by update_data into SQLite databases.

.. raw:: html
    <!--
    * Copyright (C) 2024 Scribe
    *
    * This program is free software: you can redistribute it and/or modify
    * it under the terms of the GNU General Public License as published by
    * the Free Software Foundation, either version 3 of the License, or
    * (at your option) any later version.
    *
    * This program is distributed in the hope that it will be useful,
    * but WITHOUT ANY WARRANTY; without even the implied warranty of
    * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    * GNU General Public License for more details.
    *
    * You should have received a copy of the GNU General Public License
    * along with this program.  If not, see <https://www.gnu.org/licenses/>.
    -->
"""

import ast
import json
import os
import sqlite3
import sys
from typing import List, Optional

from tqdm.auto import tqdm

from scribe_data.utils import (
    DEFAULT_JSON_EXPORT_DIR,
    DEFAULT_SQLITE_EXPORT_DIR,
    get_language_iso,
)


def data_to_sqlite(
    languages: Optional[List[str]] = None, specific_tables: Optional[List[str]] = None
) -> None:
    PATH_TO_SCRIBE_DATA = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    with open(
        f"{PATH_TO_SCRIBE_DATA}/load/update_files/total_data.json", encoding="utf-8"
    ) as f:
        current_data = json.load(f)

    current_languages = list(current_data.keys())
    data_types = [
        "nouns",
        "verbs",
        "prepositions",
        "translations",
        "autosuggestions",
        "emoji_keywords",
    ]

    if not languages:
        languages = current_languages

    if not set(languages).issubset(current_languages):
        raise ValueError(
            f"Invalid language(s) specified. Available languages are: {', '.join(current_languages)}"
        )

    # Prepare data types to process.
    language_data_type_dict = {
        lang: [
            f.split(".json")[0]
            for f in os.listdir(
                f"{PATH_TO_SCRIBE_DATA}/../../{DEFAULT_JSON_EXPORT_DIR}/{lang}"
            )
            if f.split(".json")[0] in (specific_tables or data_types)
        ]
        for lang in languages
    }

    if specific_tables and "autocomplete_lexicon" in specific_tables:
        for lang in language_data_type_dict:
            if "autocomplete_lexicon" not in language_data_type_dict[lang]:
                language_data_type_dict[lang].append("autocomplete_lexicon")

    print(
        f"Creating/Updating SQLite databases for the following languages: {', '.join(languages)}"
    )
    if specific_tables:
        print(f"Updating only the following tables: {', '.join(specific_tables)}")

    for lang in tqdm(
        language_data_type_dict,
        desc="Databases created",
        unit="dbs",
    ):
        if language_data_type_dict[lang] != []:
            maybe_over = ""  # output string formatting variable (see below)
            if os.path.exists(
                f"{PATH_TO_SCRIBE_DATA}/../../{DEFAULT_SQLITE_EXPORT_DIR}/{get_language_iso(lang).upper()}LanguageData.sqlite"
            ):
                os.remove(
                    f"{PATH_TO_SCRIBE_DATA}/../../{DEFAULT_SQLITE_EXPORT_DIR}/{get_language_iso(lang).upper()}LanguageData.sqlite"
                )
                maybe_over = "over"

            connection = sqlite3.connect(
                f"{PATH_TO_SCRIBE_DATA}/../../{DEFAULT_SQLITE_EXPORT_DIR}/{get_language_iso(lang).upper()}LanguageData.sqlite"
            )
            cursor = connection.cursor()

            def create_table(data_type, cols):
                """
                Creates a table in the language database given a data type for its title and column names.

                Parameters
                ----------
                    data_type : str
                        The name of the table to be created

                    cols : list of strings
                        The names of columns for the new table
                """
                cursor.execute(
                    f"CREATE TABLE IF NOT EXISTS {data_type} ({' Text, '.join(cols)} Text, UNIQUE({cols[0]}))"
                )

            def table_insert(data_type, keys):
                """
                Inserts a row into a language database table.

                Parameters
                ----------
                    data_type : str
                        The name of the table to be inserted into

                    keys : list of strings
                        The values to be inserted into the table row
                """
                insert_question_marks = ", ".join(["?"] * len(keys))
                cursor.execute(
                    f"INSERT OR IGNORE INTO {data_type} values({insert_question_marks})",
                    keys,
                )

            print(f"Database for {lang} {maybe_over}written and connection made.")
            for dt in language_data_type_dict[lang]:
                if dt == "autocomplete_lexicon":
                    continue  # We'll handle this separately

                print(f"Creating/Updating {lang} {dt} table...")
                json_file_path = f"{PATH_TO_SCRIBE_DATA}/../../{DEFAULT_JSON_EXPORT_DIR}/{lang}/{dt}.json"

                if not os.path.exists(json_file_path):
                    print(
                        f"Skipping {lang} {dt} table creation as JSON file not found."
                    )
                    continue
                with open(json_file_path, "r", encoding="utf-8") as f:
                    json_data = json.load(f)

                if dt == "nouns":
                    cols = ["noun", "plural", "form"]
                    create_table(data_type=dt, cols=cols)
                    cursor.execute(f"DELETE FROM {dt}")  # Clear existing data
                    for row in json_data:
                        keys = [row, json_data[row]["plural"], json_data[row]["form"]]
                        table_insert(data_type=dt, keys=keys)

                    if "Scribe" not in json_data and lang != "Russian":
                        table_insert(data_type=dt, keys=["Scribe", "Scribes", ""])

                    connection.commit()

                elif dt == "verbs":
                    cols = ["verb"]
                    cols += json_data[list(json_data.keys())[0]].keys()
                    create_table(data_type=dt, cols=cols)
                    cursor.execute(f"DELETE FROM {dt}")  # Clear existing data
                    for row in json_data:
                        keys = [row]
                        keys += [json_data[row][col_name] for col_name in cols[1:]]
                        table_insert(data_type=dt, keys=keys)

                elif dt in ["prepositions", "translations"]:
                    if dt == "prepositions":
                        cols = ["preposition", "form"]
                    else:  # translations
                        cols = ["word", "translation"]
                    create_table(data_type=dt, cols=cols)
                    cursor.execute(f"DELETE FROM {dt}")  # Clear existing data
                    for row in json_data:
                        keys = [row, json_data[row]]
                        table_insert(data_type=dt, keys=keys)

                elif dt in ["autosuggestions", "emoji_keywords"]:
                    cols = ["word"] + [f"{dt[:-1]}_{i}" for i in range(3)]
                    create_table(data_type=dt, cols=cols)
                    cursor.execute(f"DELETE FROM {dt}")  # Clear existing data
                    for row in json_data:
                        keys = [row]
                        if dt == "autosuggestions":
                            keys += [
                                json_data[row][i] for i in range(len(json_data[row]))
                            ]
                        else:  # emoji_keywords
                            keys += [
                                json_data[row][i]["emoji"]
                                for i in range(len(json_data[row]))
                            ]
                        keys += [""] * (len(cols) - len(keys))
                        table_insert(data_type=dt, keys=keys)

                connection.commit()

            # Handle autocomplete_lexicon separately
            if (not specific_tables or "autocomplete_lexicon" in specific_tables) and {
                "nouns",
                "prepositions",
                "autosuggestions",
                "emoji_keywords",
            }.issubset(set(language_data_type_dict[lang] + (specific_tables or []))):
                print(f"Creating/Updating {lang} autocomplete_lexicon table...")
                cols = ["word"]
                create_table(data_type="autocomplete_lexicon", cols=cols)
                cursor.execute(
                    "DELETE FROM autocomplete_lexicon"
                )  # Clear existing data

                sql_query = """
                INSERT INTO autocomplete_lexicon (word)

                WITH full_lexicon AS (
                    SELECT
                    noun AS word
                    FROM
                    nouns
                    WHERE
                    LENGTH(noun) > 2

                    UNION

                    SELECT
                    preposition AS word
                    FROM
                    prepositions
                    WHERE
                    LENGTH(preposition) > 2

                    UNION

                    SELECT DISTINCT
                    -- For autosuggestion keys we want lower case versions.
                    -- The SELECT DISTINCT cases later will make sure that nouns are appropriately selected.
                    LOWER(word) AS word
                    FROM
                    autosuggestions
                    WHERE
                    LENGTH(word) > 2

                    UNION

                    SELECT
                    word AS word
                    FROM
                    emoji_keywords
                )

                SELECT DISTINCT
                    -- Select an upper case noun if it's available.
                    CASE
                        WHEN
                            UPPER(SUBSTR(lex.word, 1, 1)) || SUBSTR(lex.word, 2) = nouns_cap.noun
                        THEN
                            nouns_cap.noun

                        WHEN
                            UPPER(lex.word) = nouns_upper.noun
                        THEN
                            nouns_upper.noun

                        ELSE
                            lex.word
                    END

                FROM
                    full_lexicon AS lex

                LEFT JOIN
                    nouns AS nouns_cap

                ON
                    UPPER(SUBSTR(lex.word, 1, 1)) || SUBSTR(lex.word, 2) = nouns_cap.noun

                LEFT JOIN
                    nouns AS nouns_upper

                ON
                    UPPER(lex.word) = nouns_upper.noun

                WHERE
                    LENGTH(lex.word) > 1
                    AND lex.word NOT LIKE '%-%'
                    AND lex.word NOT LIKE '%/%'
                    AND lex.word NOT LIKE '%(%'
                    AND lex.word NOT LIKE '%)%'
                    AND lex.word NOT LIKE '%"%'
                    AND lex.word NOT LIKE '%“%'
                    AND lex.word NOT LIKE '%„%'
                    AND lex.word NOT LIKE '%”%'
                    AND lex.word NOT LIKE "%'%"
                """

                try:
                    cursor.execute(sql_query)
                    connection.commit()
                    print(
                        f"{lang} autocomplete_lexicon table created/updated successfully."
                    )
                except sqlite3.Error as e:
                    print(f"Error creating/updating autocomplete_lexicon table: {e}")

            connection.close()
            print(f"{lang} database processing completed.")
        else:
            print(
                f"Skipping {lang} database creation/update as no relevant JSON data files were found."
            )

    print("Database creation/update process completed.")


if __name__ == "__main__":
    languages = ast.literal_eval(sys.argv[1]) if len(sys.argv) >= 2 else None
    specific_tables = ast.literal_eval(sys.argv[2]) if len(sys.argv) == 3 else None

    data_to_sqlite(languages, specific_tables)
