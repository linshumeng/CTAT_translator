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

class mass_produce:
    """the class for mass production purpose"""
    def __init__(self, infile_brd, infile_table, outfile_folder):
        self.infile_brd = infile_brd
        self.infile_table = infile_table
        self.outfile_folder = outfile_folder

    def replace_var(self):
        """replace variable with value in the latest mass production table"""
        table_clean = pd.read_csv(self.infile_table, sep="\t", index_col=0, keep_default_na=False)
        for column in range(table_clean.shape[1]):
            for row in range(table_clean.shape[0]):
                content_new = str(table_clean.iloc[row, column])
                pattern_variable = "%\((.*?)\)%"
                # count the number of the replacement in one variable(content_new)
                match_variable = [match for match in re.findall(pattern_variable, str(content_new))]
                for i in range(len(match_variable)):
                    # find the variable
                    variable = "%(" + str(match_variable[i]) + ")%"
                    # find the corresponding column name, and then find the value
                    column_name = table_clean.columns[column]
                    try:
                        value = table_clean.loc[variable, column_name] 
                        # print(variable, value)
                        content_new = content_new.replace(variable, value)
                        table_clean.iloc[row, column] = content_new
                    except:
                        print(column_name, variable + " doesn't exist")
        return table_clean

    def function_format(self, content_new):
        pattern_function = "<%(.*?)%>"
        # count the number of functions in one variable(content_new)
        match_function = [match for match in re.findall(pattern_function, str(content_new))]
        if match_function:
            for i in range(len(match_function)):
                function = "<%" + str(match_function[i]) + "%>"
                match_function[i] = match_function[i].replace('"', "&quot;")
                function_new = "&lt;%" + str(match_function[i]) + "%&gt;"
                content_new = content_new.replace(function, function_new)
        return content_new
    
    def mass_produce_file(self):
        """iterate and mass produce all the brds"""
        table_clean = self.replace_var()
        for i in range(len(table_clean.columns)):
            column_name = table_clean.columns[i]
            fout = self.outfile_folder + str(table_clean.columns[i]) + ".brd"
            count_line = 0
            count_text = 0
            count_name = 0
            with open(self.infile_brd, 'r') as infile, open(fout, 'w+') as outfile:
                for line in infile:
                    line = line.replace('\r', '')
                    line_str = str(line)
                    # replace massproduce
                    if count_name == 0:
                        pattern_problem_name_1 = "<ProblemName>(.*?)</ProblemName>"
                        match_problem_name_1 = [match for match in re.findall(pattern_problem_name_1, str(line_str))]
                        pattern_problem_name_2 = "<ProblemName />"
                        match_problem_name_2 = [match for match in re.findall(pattern_problem_name_2, str(line_str))]
                        problem_name = "<ProblemName>" + str(column_name) + "</ProblemName>"
                        if match_problem_name_1:
                            line_str = line_str.replace(match_problem_name_1[0], str(column_name))
                            # print(line_str)
                            count_name += 1
                        elif match_problem_name_2:
                            line_str = line_str.replace(match_problem_name_2[0], problem_name)
                            # print(line_str)
                            count_name += 1
                        else:
                            pass
                    # replace text in first node
                    if count_text == 0:
                        pattern_first_node_1 = "<text>(.*?)</text>"
                        match_first_node_1 = [match for match in re.findall(pattern_first_node_1, str(line_str))]
                        pattern_first_node_2 = "<text />"
                        match_first_node_2 = [match for match in re.findall(pattern_first_node_2, str(line_str))]
                        node_name = "<text>" + str(column_name) + "</text>"
                        if match_first_node_1:
                            line_str = line_str.replace(match_first_node_1[0], str(column_name))
                            count_text += 1
                        elif match_first_node_2:
                            line_str = line_str.replace(match_first_node_2[0], node_name)
                            count_text += 1
                        else:
                            pass
                    # count the number of the replacement in one variable(line_str)
                    pattern_variable = "%\((.*?)\)%"
                    match_variable = [match for match in re.findall(pattern_variable, str(line_str))]
                    if match_variable == []:
                        line_str = line_str
                    else:
                        for j in range(len(match_variable)):
                            # find the variable
                            variable = "%(" + str(match_variable[j]) + ")%"
                            # find the corresponding column name, and then find the value
                            try:
                                value = table_clean.loc[variable, column_name] 
                                line_str = line_str.replace(variable, value)
                                line_str = self.function_format(line_str)
                                # line_str = line_str.replace(variable, value).replace("<%", "&lt;%").replace("%>", "%&gt;")
                            except:
                                print(column_name, variable + " doesn't exist") 
                    count_line += 1
                    outfile.write(line_str)
                print(fout.split("/")[-1] + " finished")

class validate():
    """the class for validation purpose"""
    def __init__(self, old_folder, new_folder):
        self.old_folder = old_folder
        self.new_folder = new_folder

    def check(self, old_brd, new_brd):
        """use ET.parse to validate"""
        old = ET.parse(old_brd)
        new = ET.parse(new_brd)
        old_text = old.getroot().itertext()
        new_text = new.getroot().itertext()
        set_old = set(old_text)
        set_new = set(new_text)
        if set_old == set_new:
            res = "True"
        else:
            res = "False"
        return set_old, set_new, res

    def check_xmldiff(self, old_brd, new_brd):
        """use xmldiff to validate"""
        diff = main.diff_files(old_brd, new_brd)
        if len(diff) == 0:
            res = "True"
        else:
            res = "False"
        return diff, res
    
    def validate_file(self):
        fs_brd = glob.glob(self.old_folder + "*")
        for old_brd in tqdm(fs_brd, position=0, leave=True):
            new_brd = self.new_folder + old_brd.split("\\", 1)[-1]
            if os.path.exists(new_brd):
                new_brd = new_brd
            elif os.path.exists(new_brd.replace('Problem', '')):
                new_brd = new_brd.replace('Problem', '')
            elif os.path.exists(new_brd.replace(old_brd.split("\\", 1)[-1], "Problem"+old_brd.split("\\", 1)[-1])):
                new_brd = new_brd.replace(old_brd.split("\\", 1)[-1], "Problem"+old_brd.split("\\", 1)[-1])
            else:
                print(old_brd.split("\\", 1)[-1], " cannot find reference")
                continue
            _, _, res_tree = self.check(old_brd, new_brd)
            _, res_diff = self.check_xmldiff(old_brd, new_brd)
            print(old_brd.split("\\", 1)[-1], res_tree, res_diff)

class translate():
    """the class for translation purpose"""
    def __init__(self, path_new, path_ref, path_output, path_no_mark, TARGET_LANG = 'es'):
        self.path_new = path_new
        self.path_ref = path_ref
        self.path_output = path_output
        self.path_no_mark = path_no_mark
        self.TARGET_LANG = TARGET_LANG

    def find_function(self, content_new, replacement="#*"):
        """find and replace function-like(<%...%>) in value"""
        replacement_sign = "#*"
        replacement_dic = {}
        pattern_function = "<%(.*?)%>"
        # count the number of the replacement in one variable(content_new)
        match_function = [match for match in re.findall(pattern_function, str(content_new))]
        if match_function:
            for i in range(len(match_function)):
                function = "<%" + str(match_function[i]) + "%>"
                replacement = replacement_sign + str(i)
                replacement_dic[replacement] = function
                content_new = content_new.replace(function, replacement)
        return content_new, replacement_dic
    
    def replace_var(self):
        """replace variable with value in the latest mass production table"""
        table_clean = pd.read_csv(self.path_new, sep="\t", index_col=0, keep_default_na=False)
        # iterate column and row in table_clean
        for column in range(table_clean.shape[1]):
            for row in range(table_clean.shape[0]):
                content_new = str(table_clean.iloc[row, column])
                content_new, replacement_dic = self.find_function(content_new)
                pattern_variable = "%\((.*?)\)%"
                # count the number of the replacement in one variable(content_new)
                match_variable = [match for match in re.findall(pattern_variable, str(content_new))]
                if bool(replacement_dic) is False:
                    pass
                else:
                    for key, value in replacement_dic.items():
                        content_new = content_new.replace(key, value)
                for i in range(len(match_variable)):
                    # find the variable
                    variable = "%(" + str(match_variable[i]) + ")%"
                    # find the corresponding column name, and then find the value
                    column_name = table_clean.columns[column]
                    try:
                        value = table_clean.loc[variable, column_name] 
                        # print(variable, value)
                        content_new = content_new.replace(variable, value)
                        table_clean.iloc[row, column] = content_new
                    except:
                        print(column_name, variable + " doesn't exist")
        return table_clean
    
    def create_table(self):
        table_clean = self.replace_var()

        # Change column name
        table_clean_col_list = []
        for i in table_clean:
            table_clean_col_list.append(i)
            table_clean_col_list.append(i+"ESP")

        # Create a new table, with the column from the Greg's mass production table and the index from the latest mass production table
        table_translated = pd.DataFrame(columns=table_clean_col_list, index=table_clean.index)
        table_translated_clean = pd.DataFrame(columns=table_clean_col_list, index=table_clean.index)

        return table_translated, table_translated_clean
    
    def translate_file(self):
        # read the Greg's mass production table
        table_old = pd.read_csv(self.path_ref, header = None)
        # skip some rows, because they are translation for HTML elements
        header_index = table_old.index[table_old[0] == 'Problem Name'].to_list()
        # reload the csv
        table_old = pd.read_csv(self.path_ref, header = header_index)

        table_clean = self.replace_var()
        table_translated, table_translated_clean = self.create_table()
        
        # find the translation of the latest mass production table from the Greg's mass production table 
        google_dict = {}
        for column in range(table_clean.shape[1]):
            for row in range(table_clean.shape[0]):
                content_new = str(table_clean.iloc[row, column])
                column_name = table_clean.columns[column]
                column_num = table_translated.columns.get_loc(column_name)
                # write the english column
                table_translated[column_name].iloc[row] = content_new
                table_translated_clean[column_name].iloc[row] = content_new
                if table_clean.index[row] == '%(startStateNodeName)%':
                    print("skip '%(startStateNodeName)%'")
                    table_translated.iloc[row, column_num+1] = content_new
                    table_translated_clean.iloc[row, column_num+1] = content_new
                else:
                    # print(content_new)
                    # digit or empty, keep the original
                    if content_new.lstrip('-').replace(".", "").isdigit() or content_new == '':
                        print("digital or empty")
                        content_translated = content_new
                        content_translated_clean = content_translated
                    # search in dict
                    elif content_new in google_dict:
                        print("find translation in dict")
                        content_translated = '[google]' + google_dict[content_new]
                        content_translated_clean = google_dict[content_new]
                    # translate in google
                    elif table_old.columns[(table_old == content_new).any()].empty:
                        print("use google translation")
                        try:
                            content_new, replacement_dic = self.find_function(content_new) 
                            translation = tss.google(content_new, from_language='en', to_language=self.TARGET_LANG)
                            print(content_new, replacement_dic)
                            if bool(replacement_dic) is False:
                                pass
                            else:
                                for key, value in replacement_dic.items():
                                    translation = translation.replace(key, value)
                        except:
                            translation = 'error'
                        content_translated = '[google]' + translation
                        content_translated_clean = translation
                        google_dict[content_new] = translation
                    # find translation in old table
                    else:
                        print("find translation in sheet")
                        column_name_old = table_old.columns[(table_old == content_new).any()][0]
                        column_num_old = table_old.columns.get_loc(column_name_old)
                        content_translated = table_old[table_old[column_name_old] == content_new].iloc[0, column_num_old+1]
                        content_translated_clean = table_old[table_old[column_name_old] == content_new].iloc[0, column_num_old+1]
                    # print(content_translated)
                    table_translated.iloc[row, column_num+1] = content_translated
                    table_translated_clean.iloc[row, column_num+1] = content_translated_clean
        
        # export the csv
        table_translated_output = table_translated.fillna("[CTAT]NAN")
        table_translated_output.to_csv(self.path_output, encoding="utf-8", sep="\t")
        table_translated_clean.to_csv(self.path_no_mark, encoding="utf-8", sep="\t")

if __name__ == "__main__":
    # run the process function
    if sys.argv[1] == 'clean':
        print("operating clean task")
        if len(sys.argv) != 6:
            print("number of input element is not enough")
        else:
            html_brd = sys.argv[2]
            html_table = sys.argv[3]
            clean_brd = sys.argv[4]
            clean_table = sys.argv[5]
            clean_res = clean(html_brd, html_table, clean_brd, clean_table)
            _, _ = clean_res.clean_file()
            # python general.py clean "./HTML_folder/7.06 HTML/7.06 HTML/MassProduction/7_06.brd" "./HTML_folder/7.06 HTML/7.06 HTML/MassProduction/7_06.txt" "./Output_cleaned_folder/7.06 HTML/7.06 HTML/MassProduction/7_06_cleaned.brd" "./Output_cleaned_folder/7.06 HTML/7.06 HTML/MassProduction/7_06_cleaned.txt"
    elif sys.argv[1] == 'validate':
        print("operating validate task")
        if len(sys.argv) != 4:
            print("number of input element is not enough")
        else:
            old_folder = sys.argv[2]
            new_folder = sys.argv[3]
            validate_clean_res = validate(old_folder, new_folder)
            validate_clean_res.validate_file()
            # python general.py validate "./HTML_folder/7.06 HTML/7.06 HTML/FinalBRDs/" "./Output_cleaned_folder/7.06 HTML/7.06 HTML/FinalBRDs/"
    elif sys.argv[1] == 'translate':
        print("operating translate task")
        if len(sys.argv) != 6:
            print("number of input element is not enough")
        else:
            clean_table = sys.argv[2]
            ref_table = sys.argv[3]
            transalte_table = sys.argv[4]
            transalte_table_no_mark = sys.argv[5]
            try:
                if sys.argv[6]:
                    target_lang = sys.argv[6]
                translate_clean_res = translate(clean_table, ref_table, transalte_table, transalte_table_no_mark, target_lang)
            except:
                translate_clean_res = translate(clean_table, ref_table, transalte_table, transalte_table_no_mark)
            translate_clean_res.translate_file()
    elif sys.argv[1] == 'mass_produce':
        print("operating mass_produce task")
        if len(sys.argv) != 5:
            print("number of input element is not enough")
        else:
            clean_brd = sys.argv[2]
            table = sys.argv[3]
            output_folder = sys.argv[4]
            mass_produce_translate_res = mass_produce(clean_brd, table, output_folder)
            mass_produce_translate_res.mass_produce_file()
    else:
        print("no task found")
