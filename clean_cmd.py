import xml.etree.ElementTree as ET
import re
from nltk.corpus import stopwords
import pandas as pd
import sys

STOPWORDS = stopwords.words('english')

# create name for variable
def clean_name(s, convert_to_lower=True):
    s = re.sub('<[^<]+?>', '', s) # markup
    s = re.sub('[^0-9a-zA-Z_\s]', '', s) # keep alnum
    s = re.sub('\t\n\r', '', s) # remove tab, line break, carriage return
    s = ' '.join(s.split()) # remove redundant whitespace
    return s.lower() if convert_to_lower else s

# remove unnecessary part in value
def clean_phrase(s, convert_to_lower=False):
    if(s is None or s == ''):
        return None
    s = re.sub('\t\n\r', '', s) # remove tab, line break, carriage return
    s = ' '.join(s.split()) # remove redundant whitespace
    return s.lower() if convert_to_lower else s

# create variable
def make_var(phrase, signature='_', keep_n_words=4):
    if (phrase is None or phrase == ''):
        return ''
    the_clean_phrase = clean_phrase(phrase) 
    # print(the_clean_phrase)
    if the_clean_phrase in var_phrase_map: # if the variable in var_phrase_map
        return var_phrase_map[the_clean_phrase]
    else:
        h = signature + '_' + '_'.join([word for word in clean_name(phrase).split(' ') if word not in STOPWORDS][:keep_n_words])
        v = '%(' + str(h) + ')%' # create variable name
        var_phrase_map[the_clean_phrase] = v # dict key: variable value, dict value: variable name
        return v

# change variable name
def change_var(old_name, signature='_', keep_n_words=4):
    if old_name in var_name_map:
        return var_name_map[old_name]
    else:
        phrase = table_new.loc[old_name].iloc[0] # find the pharse in the mass production table
        if (old_name is None or old_name == '' or pd.isnull(phrase)):
            return ''
        the_clean_phrase = clean_phrase(phrase) 
        h = signature + '_' + '_'.join([word for word in clean_name(phrase).split(' ') if word not in STOPWORDS][:keep_n_words])
        v = '%(' + str(h) + ')%'
        var_name_map[old_name] = v
        table_new.rename(index={old_name:v}, inplace=True) # dict key: variable value, dict value: variable name
        return v

# find hash
def find_hash(s):
    if(s is None or s == ''):
        return False
    # replace "%(" and "%)" to detect whether the variable name is a hash-like
    s = re.sub('%\(', '', s) # "\" is for re
    s = re.sub('\)%', '', s)
    return s.lstrip('-').isdigit()

# replace pharse with variable
def iterate_generic(tag: str, root):
    """txt should be %% type or a pharse."""
    table_new_index_list = table_new.index.tolist() 
    count = 1
    for element in root.iter(tag):
        if tag == 'Input' and element[0].tag == 'value': # find input value
            txt = element[0].text
        else:
            txt = element.text
        # if txt is empty
        if clean_phrase(txt) is None or clean_phrase(txt) == '':
            continue
        # elif txt is already in the mass production table and it is not a hash-like
        elif txt in table_new_index_list and find_hash(txt) is False:
            continue
        # elif txt is already in the mass production table and it is a hash-like
        elif txt in table_new_index_list and find_hash(txt) is True:
            if tag == 'Input':
                element[0].text = change_var(txt, signature=tag+'_'+str(count))
            else:
                element.text = change_var(txt, signature=tag+'_'+str(count))
        # else create a variable name for the value
        else:
            if tag == 'Input':
                element[0].text = make_var(txt, signature=tag+'_'+str(count))
            else:
                element.text = make_var(txt, signature=tag+'_'+str(count))
        count += 1

# read the tags and call all functions above
def process_file(infile_brd, infile_table, outfile_brd, outfile_table):
    global tree; tree = ET.parse(infile_brd)
    print("mass production brd input read")
    print("path: " + infile_brd)
    root = tree.getroot()
    global var_phrase_map; var_phrase_map = dict()
    global var_name_map; var_name_map = dict()

    global table_new; table_new = pd.read_csv(infile_table, sep="\t", index_col=0)
    print("mass production table input read")
    print("path: " + infile_table)

    tags = ['hintMessage', 'buggyMessage', 'successMessage', 
            'label', 'Input']
    for tag in tags:
        iterate_generic(tag, root) 

    # create new dataframe and concat it with the latest mass production table
    df_new = pd.DataFrame(var_phrase_map.keys(), index = list(var_phrase_map.values()))
    df_dup = pd.concat([df_new.T]*len(table_new.columns)).T
    df_dup.columns = table_new.columns
    df_mix = pd.concat([table_new, df_dup])

    # export the csv
    df_mix.to_csv(outfile_table, encoding="utf-8", sep="\t")
    print("mass production table output finished")
    print("path: " + outfile_table)

    # export the brd
    tree.write(outfile_brd)
    print("mass production brd output finished")
    print("path: " + outfile_table)

    return

# read the latest mass production graph and mass production table
try:
    infile_brd =sys.argv[1]
    print("using argument 1 as brd input")
except:
    infile_brd = "./HTML_folder/7.17 HTML/7.17 HTML/MassProduction/7-17_finalTemplate_new.brd"
try:
    infile_table = sys.argv[2]
    print("using argument 2 as table input")
except:
    infile_table = "./HTML_folder/7.17 HTML/7.17 HTML/MassProduction/7-17_finalMassProduction_new.txt"

# set the output paths
try:
    outfile_brd = sys.argv[3]
    print("using argument 3 as brd output")
except:
    outfile_brd = infile_brd.replace('/HTML_folder/7.17 HTML/7.17 HTML/MassProduction/', '/Output_cleaned_folder/').replace('.brd', '_cleaned.brd')
try:
    outfile_table = sys.argv[4]
    print("using argument 4 as table output")
except:
    outfile_table = infile_table.replace('/HTML_folder/7.17 HTML/7.17 HTML/MassProduction/', '/Output_cleaned_folder/').replace('.txt', '_cleaned.txt')

# run the process function
process_file(infile_brd, infile_table, outfile_brd, outfile_table)