"""Dated integration decisions; no restricted platform is fetched."""
VERIFIED_AT="2026-10-10T00:00:00+00:00"
PLATFORMS=[
("Wellfound","https://wellfound.com/jobs","MANUAL_IMPORT"),("YC Jobs","https://www.ycombinator.com/jobs","MANUAL_IMPORT"),("Welcome to the Jungle / Otta","https://www.welcometothejungle.com/en/jobs","ALERT_IMPORT"),("Hirect","https://hirect.in/","MANUAL_IMPORT"),("Upraised","https://jobs.upraised.co/","UNVERIFIED"),
("Instahyre","https://www.instahyre.com/","ALERT_IMPORT"),("Cutshort","https://cutshort.io/jobs","ALERT_IMPORT"),("Hirist","https://www.hirist.tech/","ALERT_IMPORT"),("IIMJobs","https://www.iimjobs.com/","ALERT_IMPORT"),("Foundit","https://www.foundit.in/","ALERT_IMPORT"),
("Remote OK","https://remoteok.com/","PUBLIC_FEED"),("We Work Remotely","https://weworkremotely.com/","PUBLIC_FEED"),("FlexJobs","https://www.flexjobs.com/","RESTRICTED"),("Turing","https://www.turing.com/jobs","MANUAL_IMPORT"),("Dice","https://www.dice.com/","AUTHORIZED_API"),
("LinkedIn","https://www.linkedin.com/jobs/","RESTRICTED"),("Naukri","https://www.naukri.com/","ALERT_IMPORT"),("Indeed","https://www.indeed.com/","RESTRICTED"),("Glassdoor","https://www.glassdoor.com/Job/","RESTRICTED"),("HackerEarth Jobs","https://www.hackerearth.com/recruit/","MANUAL_IMPORT")]

def records():
    for name,url,state in PLATFORMS:
        yield (name,url,state,"OPERATING","Public feed" if state=="PUBLIC_FEED" else "No anonymous supported read feed verified","None" if state in {"PUBLIC_FEED","MANUAL_IMPORT","ALERT_IMPORT"} else "Authorization/account may be required","India relevant" if name not in {"FlexJobs","Dice"} else "Limited India focus","Available" if state=="PUBLIC_FEED" else "Varies",VERIFIED_AT,"Classified conservatively from official site/help/terms; direct extraction enabled only for documented public feeds.")
