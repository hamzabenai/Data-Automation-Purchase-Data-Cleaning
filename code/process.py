import streamlit as st
import google.generativeai as genai
import pandas as pd
import re
import time
from dotenv import load_dotenv
import os

load_dotenv()
api_key = os.getenv('API_KEY')

# Streamlit app title
st.title("Data Cleaning and Mapping Tool")

# Function to load commune data
def load_material_data():
    commune_data = pd.read_excel(r'\automation\data\process_data.xlsx', sheet_name='communes')
    return commune_data

# Function to load input data
def load_input_data(uploaded_file):
    df = pd.read_excel(uploaded_file)
    return df

# Function to clean data
def cleaning_data(df):
    df = df.drop(columns=['status', 'EXPEDITION'])
    df = df[['الاسم و لقب', 'رقم الهاتف', 'الولاية', 'العنوان', 'produits', 'السعر', 'comment-3', 'comment-1', 'comment-2']]
    df['reference'] = df['produits']
    df.insert(0, 'reference', df.pop('reference'))
    df[['comment-1', 'comment-2', 'comment-3']] = df[['comment-1', 'comment-2', 'comment-3']].astype(str)
    df['remarque'] = df['comment-3'] + '+' + df['comment-1'] + '+' + df['comment-2']
    df = df.drop(columns=['comment-3', 'comment-1', 'comment-2'])
    df.rename(columns={'الاسم و لقب': 'nom et prenom du destinataire*', 'رقم الهاتف': 'telephone*', 'الولاية': 'wilaya de livraison', 'العنوان': 'adresse de livraison*', 'produits': 'produit (référence)*', 'السعر': 'montant du colis*'}, inplace=True)
    df['nom et prenom du destinataire*'].fillna('pas de nom', inplace=True)
    df['telephone 2'] = None
    df['code wilaya*'] = None
    df['commune de livraison*'] = None
    df['poids (kg)'] = None
    df['FRAGILE'] = None
    df['OUVRIR'] = None
    df['ECHANGE'] = None
    df['STOP DESK'] = None
    df['Lien map'] = None
    df = df[['reference', 'nom et prenom du destinataire*', 'telephone*', 'telephone 2', 'code wilaya*', 'wilaya de livraison', 'commune de livraison*', 'adresse de livraison*', 'produit (référence)*', 'poids (kg)', 'montant du colis*', 'remarque', 'FRAGILE', 'OUVRIR', 'ECHANGE', 'STOP DESK', 'Lien map']]
    df['telephone*'] = df['telephone*'].astype(str)
    df['telephone*'] = df['telephone*'].str.replace(' ', '')
    df['telephone*'] = '0' + df['telephone*']
    return df

def load_model():
    genai.configure(api_key="AIzaSyCggDnTG__jpKsRNaMiclJDEGucy4PqobA")
    model = genai.GenerativeModel('gemini-2.0-flash')
    return model

def mapping_code_commune(commune_data, df, model):
    commune_names = commune_data['nom communes'].tolist()
    wilaya_info = {}
    cooldown_time = 5  

    progress_bar = st.progress(0)
    total_rows = len(df)
    
    for index, row in df.iterrows():
        wilaya = row['wilaya de livraison']
        address = row['adresse de livraison*']
        try:
            response_text = get_wilaya_info(wilaya, address, commune_names, model)
            code_wilaya, nom_commune = extract_info(response_text)
            
            wilaya_info[wilaya] = {
                "code wilaya": code_wilaya,
                "nom commune": nom_commune,
                "wilaya de livraison": wilaya,
                "adresse de livraison*": address
            }
            
            # Update progress bar
            progress = (index + 1) / total_rows
            progress_bar.progress(progress)
            
            time.sleep(cooldown_time)
        except Exception as e:
            print(f"Error processing {wilaya}: {e}")
            wilaya_info[wilaya] = {
                "code wilaya": None,
                "nom commune": None,
                "wilaya de livraison": wilaya,
                "adresse de livraison*": address
            }
    return wilaya_info

def get_wilaya_info(wilaya_name, address, commune_names, model):
    prompt = f'''For the wilaya: {wilaya_name} in Algeria and address: {address}, provide the 'code wilaya' and 'nom commune'.
    The 'nom commune' must be one of the following: {", ".join(commune_names)}.
    Use the following format:
    "code wilaya": "XX",
    "nom commune": "XXXXX"
    Ensure the response contains only the code wilaya as a two-digit number and the nom commune as a string from the provided list.'''
    response = model.generate_content(prompt)
    return response.text

def extract_info(response_text):
    code_wilaya_match = re.search(r'"code wilaya":\s*"(\d{2})"', response_text)
    nom_commune_match = re.search(r'"nom commune":\s*"([^"]+)"', response_text)
    
    code_wilaya = code_wilaya_match.group(1) if code_wilaya_match else None
    nom_commune = nom_commune_match.group(1) if nom_commune_match else None
    
    return code_wilaya, nom_commune

def assign_map_values(df, wilaya_info):
    df['code wilaya*'] = df['wilaya de livraison'].map(lambda x: wilaya_info[x]['code wilaya'])
    df['commune de livraison*'] = df['wilaya de livraison'].map(lambda x: wilaya_info[x]['nom commune'])
    return df

def main():
    commune_data = load_material_data()
    uploaded_file = st.file_uploader("Upload your raw data file (Excel)", type=["xlsx"])
    
    if uploaded_file is not None:
        df = load_input_data(uploaded_file)
        df = cleaning_data(df)

        model = load_model()

        with st.spinner("Mapping code wilaya and commune..."):
            wilaya_info = mapping_code_commune(commune_data, df, model)

        df = assign_map_values(df, wilaya_info)

        st.write("Cleaned Data:")
        st.dataframe(df)

        st.download_button(
            label="Download Cleaned Data as CSV",
            data=df.to_csv(index=False).encode('utf-8'),
            file_name="cleaned_data.csv",
            mime="text/csv"
        )

if __name__ == "__main__":
    main()
