import random
import smtplib
from collections import deque
from typing import List, Tuple
from decouple import config

from app.models import Person


def matchup(friends: List[Person]) -> List[Tuple[Person, Person]]:
    random.shuffle(friends)
    secret_friends = deque(friends)
    secret_friends.rotate()
    return list(zip(friends, secret_friends))


def send_email(persons: List[Tuple[Person, Person]], title: str, budget: str) -> bool:
    smtp_port = config("smtp_port", cast=int, default=587)
    smtp_server_domain_name = config(
        "smtp_server_domain_name", cast=str, default="smtp.gmail.com"
    )
    sender_mail = config("sender_mail", cast=str, default="")
    smtp_password = config("smtp_password", cast=str, default="")

    # creates SMTP session
    service = smtplib.SMTP(smtp_server_domain_name, smtp_port)
      
    # start TLS for security
    service.starttls()
      
    # Authentication 
    service.login(sender_mail, smtp_password)

    mail_status = True
    for friends in persons:
        content = f"{friends[1].name} o teu amigo secreto: {friends[1].name}.\n\nCompra-lhe uma prenda porreira no valor de {budget}\n"
        status = service.sendmail(from_addr=sender_mail, to_addrs=friends[0].email, msg=f"Subject: {title}\n{content}".encode('utf-8'))
        if len(status) > 0:
          mail_status = False

    service.quit()

    return mail_status
