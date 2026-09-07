"""Bounded operational logs; private chat and passwords are not recorded."""
import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path

def configure():
    root=Path(os.getenv('LOG_DIR','logs'));root.mkdir(parents=True,exist_ok=True)
    handlers=[]
    for name,level,logger in [('server.log',logging.INFO,logging.getLogger()),('error.log',logging.ERROR,logging.getLogger()),('chat.log',logging.INFO,logging.getLogger('chrozal.public_chat'))]:
        h=RotatingFileHandler(root/name,maxBytes=5_000_000,backupCount=3,encoding='utf-8')
        h.setLevel(level);h.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(name)s %(message)s'))
        logger.addHandler(h);handlers.append((logger,h))
    return handlers
