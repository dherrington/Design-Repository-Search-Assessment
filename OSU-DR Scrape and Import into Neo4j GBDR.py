#!/usr/bin/env python
# coding: utf-8

# In[ ]:


import requests
from bs4 import BeautifulSoup
import time
from IPython.display import IFrame
from neo4j import GraphDatabase
tic = time.time()


# ##### Extract main page from Oregon State University Design Repository (OSU-DR)
# 
# 1) Beautiful Soup extract of page content, limited to left bar on side of screen

# In[ ]:


URL = 'http://ftest.mime.oregonstate.edu/repo/browse/'
page = requests.get(URL)
soup = BeautifulSoup(page.content, 'html.parser')
results = soup.find(id='wholelist')
sys_elems = results.find_all('li') 


# #### Save 'System name' and system page location for entire list in OSU database
# 

# In[ ]:


links = [a['href'] for a in results.find_all('a', href=True)] #all
#links = [a['href'] for a in results.find_all('a', href=True,limit=5)] #just first 12
sys_names = [a.contents for a in results.find_all('a',href=True)] 
#sys_names = [a.contents for a in results.find_all('a',href=True,limit=5)]  #just first 12


# __Save information from each OSU-DR System Page__
# 
# 1. Save 'System Description' in list (one item per system) 
# 2. Save 'System Type' in list (one item per system)
# 3. Save 'Top Level Artifact' in list (one item per system)
# 4. Save a list of links to artifact page for each system (one list per system)
# 5. Save a list of artifact names for each system (one list per system)

# In[ ]:


system_description = [None] * len(links)
system_type = [None] * len(links)
system_top_art = [None] * len(links)
artifact_links = [None] * len(links)
artifact_names = [None] * len(links)

#for sys_link in links:
for a in range(0,len(links)):
    URL = 'http://ftest.mime.oregonstate.edu' + links[a]
    page = requests.get(URL)
    soup = BeautifulSoup(page.content, 'html.parser')
    results = soup.find('div', class_='description')
     
    if (results is not None):
        description_text = results.text.splitlines()
        for i in range(0,len(description_text)):
            #Save basic data into lists
            if((description_text[i].strip() == 'Description:') and (description_text[i+1].strip() != 'System Type' )):
                system_description[a] = description_text[i+1].strip() #Description
            
            if((description_text[i].strip() == 'System Type') and (description_text[i+1].strip() != 'Top Artifact' )):
                system_type[a] = description_text[i+1].strip() #System Type
            
            if((description_text[i].strip() == 'Top Artifact') and (description_text[i+1].strip() != 'Useful Diagrams' )):
                system_top_art[a] = description_text[i+1].strip() #System Top Artifact
    
        soup.find('div', id='leftbar').decompose()
        soup.find('div', id='navlist').decompose()
        soup.find('a', string = 'Function Model').decompose()
        soup.find('a', string = 'Assembly Model').decompose()
        artifact_list = soup.find_all('a', href=True)
        artifact_links[a] = [a['href'] for a in soup.find_all('a', href=True)]
        artifact_names[a] = [a.contents for a in soup.find_all('a',href=True)]             


# __Scrape all artifact pages, save child assembly elements__
# 
# 1. For each artifact link (iterate through each system's artifact list), save a list of child elements

# In[ ]:


parent_artifacts = [None] * len(artifact_names)
artifact_functions = [None] * len(artifact_names)
count = 0;
for a in range(0,len(artifact_names)):
    if artifact_names[a] is not None:
        parent_artifacts[a] = [None]*len(artifact_names[a])
        artifact_functions[a] = [None]*len(artifact_names[a])
        count = count + len(artifact_names[a])
        for b in range(0,len(artifact_names[a])):
            URL = 'http://ftest.mime.oregonstate.edu' + artifact_links[a][b]
            page = requests.get(URL)
            soup = BeautifulSoup(page.content, 'html.parser')
            results = soup.find('div', class_='description')
            if results.find_all(string="Child artifact") is not None:
                try:
                    parent_artifacts[a][b] = results.find('a',href=True).contents   
                except Exception:
                    pass
            if results.find_all('div', class_ = 'function') is not None:
                functions = results.find_all('div', class_ = 'function')
                artifact_functions[a][b] = [x.contents for x in functions]
            
                               


# In[ ]:


driver = GraphDatabase.driver("bolt://localhost:7687", auth=("neo4j", "1234567890"), encrypted = False)

#----------------------System Addition Functions for adding to Neo4j via Bolt------

def add_system(tx, name):
    tx.run("MERGE (a:System {name: $name}) "
           ,name=name)
        
def set_system_description(tx, name, system_desc):
    tx.run("MATCH (a:System {name: $name}) SET a.system_description = $system_desc"
           ,name=name,system_desc=system_desc)
    
def set_system_type(tx, name, system_type):
    tx.run("MATCH (a:System {name: $name}) SET a.system_type = $system_type"
           ,name=name,system_type=system_type)
    
#----------------------Artifact Addition Functions for adding to Neo4j via Bolt------

def add_artifact(tx, name):
    tx.run("MERGE (a:Artifact {name: $name}) "
           ,name=name)
    
def create_artifact_relationship(tx, parent, child, system):
    tx.run("MATCH (a:Artifact) , (b:Artifact) WHERE a.name = $parent and b.name = $child "
           "MERGE (b)-[r:CHILD_OF { sys_assoc: $system }]->(a)"
           ,parent=parent,child=child,system=system)
    
def create_sys_art_relationship(tx, parent, child, system):
    tx.run("MATCH (a:System) , (b:Artifact) WHERE a.name = $parent and b.name = $child "
           "MERGE (b)-[r:CHILD_OF { sys_assoc: $system }]->(a)"
           ,parent=parent,child=child,system=system)
    

#----------------------Function Addition Functions for adding to Neo4j via Bolt------

def add_function(tx, name):
    tx.run("MERGE (a:Function {name: $name}) "
           ,name=name)    
    
def add_art_funct_relationship(tx,artifact,function,system):
    tx.run("MATCH (a:Artifact) , (b:Function) WHERE a.name = $artifact and b.name = $function "
           "MERGE (a)-[r:Performs { sys_assoc: $system }]->(b)"
           ,artifact=artifact,function=function,system=system)
    
    
    
#----------------------Calls for Neo4j session to process transactions---------
    
with driver.session() as session:
    for i in range (0,len(sys_names)):
        session.write_transaction(add_system, sys_names[i][0])
                
        if system_description[i] is not None:
            session.write_transaction(set_system_description,sys_names[i][0],system_description[i])
        
        if system_type[i] is not None:
            session.write_transaction(set_system_type,sys_names[i][0],system_type[i])
        
                
    for i in range (0,len(artifact_names)):
        if artifact_names[i] is not None:
            for j in range (0,len(artifact_names[i])):
                if artifact_names[i][j] is not None:
                    session.write_transaction(add_artifact,artifact_names[i][j])
                    if parent_artifacts[i][j] is not None:
                        session.write_transaction(create_artifact_relationship,parent_artifacts[i][j],artifact_names[i][j],sys_names[i][0])
                        
            session.write_transaction(create_sys_art_relationship,sys_names[i][0],artifact_names[i][0],sys_names[i][0])
    
    for i in range (0,len(artifact_functions)):
        if artifact_functions[i] is not None:
            for j in range (0,len(artifact_functions[i])):
                if artifact_functions[i][j] is not None:
                    for k in range (0,len(artifact_functions[i][j])):
                        session.write_transaction(add_function,artifact_functions[i][j][k])
                        session.write_transaction(add_art_funct_relationship,artifact_names[i][j],artifact_functions[i][j][k],sys_names[i][0])
        
driver.close()


# In[ ]:


#Output runtime since start
toc = time.time()
print(toc-tic)


# In[ ]:


print(artifact_names[140])

