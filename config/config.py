import os
import yaml

path = os.path.dirname(os.path.abspath(__file__))

class Config:
    def __init__(self):
        with open(os.path.join(path, "cfg.yaml"), "r") as f:
            self.config = yaml.safe_load(f)
    def update_cookies(self,domain:str, cookies:str):
        if domain in self.config:
            self.config[domain]["headers"]["cookies"] = cookies
            with open(os.path.join(path, "cfg.yaml"), "w", encoding="utf-8") as f:
                yaml.dump(self.config, f, allow_unicode=True)
            return True
        return False
            