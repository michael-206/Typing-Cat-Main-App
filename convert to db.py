from app import db, app
from app import VocabList

with app.app_context():
    with open("all_vocab.txt", encoding="utf-8") as f:
        lines = f.readlines()
        for line in lines:
            line = line.split(":")
            name = line[0].split(", ")
            name[0] = name[0].upper()
            name[1] = name[1].title()
            cme_number = name[0][-1]
            lesson_number = name[1][6:]
            vocab_list = VocabList(name=f"CME{cme_number} Lesson{lesson_number}", _words=line[1].strip(), level=f"cme{cme_number}")
            db.session.add(vocab_list)
            db.session.commit()