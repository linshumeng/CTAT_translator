import xml.etree.ElementTree as ET
import re
from nltk.corpus import stopwords
import pandas as pd
import glob
from tqdm import tqdm
from xmldiff import main
import os
import translators.server as tss
import sys

STOPWORDS = stopwords.words('english')

class clean():
    """the class for cleaning purpose"""
    def __init__(self, infile_brd, infile_table, outfile_brd, outfile_table):
        self.infile_brd = infile_brd
        self.infile_table = infile_table
        self.outfile_brd = outfile_brd
        self.outfile_table = outfile_table
        self.var_phrase_map = dict()
        self.var_name_map = dict()
        self.table_new = None
        self.table_new_index_list = None

    def clean_name(self, s, convert_to_lower=True):
        """create name for variables in .brd"""
        s = re.sub('<[^<]+?>', '', s) # markup
        s = re.sub('[^0-9a-zA-Z_\s]', '', s) # keep alnum
        s = re.sub('\t\n\r', '', s) # remove tab, line break, carriage return
        s = ' '.join(s.split()) # remove redundant whitespace
        return s.lower() if convert_to_lower else s
    
    def clean_phrase(self, s, convert_to_lower=False):
        """remove unnecessary part in value"""
        if(s is None or s == ''):
            return None
        s = re.sub('\t\n\r', '', s) # remove tab, line break, carriage return
        s = ' '.join(s.split()) # remove redundant whitespace
        return s.lower() if convert_to_lower else s

    def find_hash(self, s):
        """find hash-like variable"""
        if(s is None or s == ''):
            return False
        # replace "%(" and "%)" to detect whether the variable is a hash-like
        s = re.sub('%\(', '', s) # "\(" is for re to search "("
        s = re.sub('\)%', '', s)
        return s.lstrip('-').isdigit() # ignore "-" in the variable 
    
    def change_var(self, old_name, signature='_', keep_n_words=4):
        """change hash-like variable's name in df"""
        if old_name in self.var_name_map:
            return self.var_name_map[old_name]
        else:
            phrase = self.table_new.loc[old_name].iloc[0] # find the first pharse in the mass production table
            if (old_name is None or old_name == '' or pd.isnull(phrase)):
                return ''
            the_clean_phrase = self.clean_phrase(phrase) 
            h = signature + '_' + '_'.join([word for word in self.clean_name(the_clean_phrase).split(' ') if word not in STOPWORDS][:keep_n_words])
            v = '%(' + str(h) + ')%'
            self.var_name_map[old_name] = v
            self.table_new.rename(index={old_name:v}, inplace=True) # dict key: variable value, dict value: variable name
            return v
    
    def make_var(self, phrase, signature='_', keep_n_words=4):
        """create variable-value pair"""
        if (phrase is None or phrase == ''):
            return ''
        the_clean_phrase = self.clean_phrase(phrase) # clean the value(phrase)
        # if the variable in self.var_phrase_map
        if the_clean_phrase in self.var_phrase_map: 
            return self.var_phrase_map[the_clean_phrase]
        # else create one
        else:
            h = signature + '_' + '_'.join([word for word in self.clean_name(the_clean_phrase).split(' ') if word not in STOPWORDS][:keep_n_words])
            v = '%(' + str(h) + ')%' # create variable name
            self.var_phrase_map[the_clean_phrase] = v # dict key: value, dict value: variable
            return v
        
    def process_txt(self, txt, element, tag, count):
        """process txt"""
        # if txt is empty
        if self.clean_phrase(txt) is None or self.clean_phrase(txt) == '':
            return
        # elif txt is already in the mass production table and it is not a hash-like
        elif txt in self.table_new_index_list and self.find_hash(txt) is False:
            return
        # elif txt is already in the mass production table and it is a hash-like
        elif txt in self.table_new_index_list and self.find_hash(txt) is True:
            if tag == 'Input':
                element[0].text = self.change_var(txt, signature=tag+'_'+str(count))
            else:
                element.text = self.change_var(txt, signature=tag+'_'+str(count))
            return
        # else create a variable name for the value
        else:
            if tag == 'Input':
                element[0].text = self.make_var(txt, signature=tag+'_'+str(count))
            else:
                element.text = self.make_var(txt, signature=tag+'_'+str(count))
            return 
    
    def iterate_generic(self, tag: str, root):
        """replace pharse with variable,
            txt should be %% type or a pharse"""
        count = 1
        for element in root.iter(tag):
            # print(tag)
            if tag == 'Input' and element[0].tag == 'value': # find input value
                txt = element[0].text
                self.process_txt(txt, element, tag, count)
            else:
                txt = element.text
                self.process_txt(txt, element, tag, count)
            count += 1

    def clean_file(self):
        """read the tags and call all functions above"""
        tree = ET.parse(self.infile_brd)
        print("mass production brd input read")
        print("path: " + self.infile_brd)
        root = tree.getroot()

        self.table_new = pd.read_csv(self.infile_table, sep="\t", index_col=0, keep_default_na=False)
        self.table_new_index_list = self.table_new.index.tolist()
        print("mass production table input read")
        print("path: " + self.infile_table)

        tags = ['hintMessage', 'successMessage', 'buggyMessage', 'label', 'Input']
        for tag in tags:
            self.iterate_generic(tag, root) 

        # create new dataframe and concat it with the latest mass production table
        df_new = pd.DataFrame(self.var_phrase_map.keys(), index = list(self.var_phrase_map.values()))
        df_dup = pd.concat([df_new.T]*len(self.table_new.columns)).T
        df_dup.columns = self.table_new.columns
        df_mix = pd.concat([self.table_new, df_dup])
        df_mix.index.name = self.table_new.index.name

        # export the csv
        df_mix.to_csv(self.outfile_table, encoding="utf-8", sep="\t")
        print("mass production table output finished")
        print("path: " + self.outfile_table)

        # export the brd
        output = open(self.outfile_brd, 'w+b')
        output.write(b'<?xml version="1.0" standalone="yes"?>\n\n')
        tree.write(output)
        print("mass production brd output finished")
        print("path: " + self.outfile_table)

        return self.table_new, df_mix

if __name__ == "__main__":
    # run the process function
    print("clean task ------")
    html_brd = sys.argv[1]
    html_table = sys.argv[2]
    clean_brd = sys.argv[3]
    clean_table = sys.argv[4]
    clean_res = clean(html_brd, html_table, clean_brd, clean_table)
    _, _ = clean_res.clean_file()

# # read the latest mass production graph and mass production table
# try:
#     infile_brd =sys.argv[1]
#     print("using argument 1 as brd input")
# except:
#     infile_brd = "./HTML_folder/7.17 HTML/7.17 HTML/MassProduction/7-17_finalTemplate_new.brd"
# try:
#     infile_table = sys.argv[2]
#     print("using argument 2 as table input")
# except:
#     infile_table = "./HTML_folder/7.17 HTML/7.17 HTML/MassProduction/7-17_finalMassProduction_new.txt"

# # set the output paths
# try:
#     outfile_brd = sys.argv[3]
#     print("using argument 3 as brd output")
# except:
#     outfile_brd = infile_brd.replace('/HTML_folder/7.17 HTML/7.17 HTML/MassProduction/', '/Output_cleaned_folder/').replace('.brd', '_cleaned.brd')
# try:
#     outfile_table = sys.argv[4]
#     print("using argument 4 as table output")
# except:
#     outfile_table = infile_table.replace('/HTML_folder/7.17 HTML/7.17 HTML/MassProduction/', '/Output_cleaned_folder/').replace('.txt', '_cleaned.txt')

# # run the process function
# process_file(infile_brd, infile_table, outfile_brd, outfile_table)