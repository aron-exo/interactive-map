from flask import Flask, render_template, request, jsonify
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv
import os
import json
from arcgis.gis import GIS
from arcgis.features import GeoAccessor, GeoSeriesAccessor
from arcgis.mapping import WebMap
import pandas as pd

app = Flask(__name__)

# Load environment variables from .env file
load_dotenv()

# Database connection function
def connect_to_database():
    try:
        conn = psycopg2.connect(
            host=os.getenv('COCKROACH_DB_HOST'),
            database=os.getenv('COCKROACH_DB_DATABASE'),
            user=os.getenv('COCKROACH_DB_USER'),
            password=os.getenv('COCKROACH_DB_PASSWORD'),
            port=os.getenv('COCKROACH_DB_PORT')
        )
        return conn
    except Exception as e:
        print(f"Connection error: {e}")
        return None

@app.route('/')
def index():
    try:
        template_path = os.path.join(app.template_folder, 'index.html')
        if os.path.exists(template_path):
            return render_template('index.html')
        else:
            return f"Template not found at {template_path}", 500
    except Exception as e:
        return str(e), 500

# Query geometries within a polygon for all relevant tables
def query_geometries_within_polygon(polygon_geojson):
    conn = connect_to_database()
    if conn is None:
        return []

    tables = get_tables_with_shape_column(conn)
    all_dataframes = []

    for table in tables:
        df = query_geometries_from_table(conn, table, polygon_geojson)
        if not df.empty:
            all_dataframes.append(df)

    conn.close()
    return all_dataframes

# Get all tables with a "SHAPE" column
def get_tables_with_shape_column(conn):
    try:
        query = """
        SELECT table_name 
        FROM information_schema.columns 
        WHERE column_name = 'SHAPE' AND table_schema = 'public';
        """
        df = pd.read_sql(query, conn)
        return df['table_name'].tolist()
    except Exception as e:
        print(f"Error fetching table names: {e}")
        return []

# Query geometries within a polygon for a specific table
def query_geometries_from_table(conn, table_name, polygon_geojson):
    try:
        query = f"""
        SELECT *, ST_AsGeoJSON(geom) as geometry
        FROM public.{table_name}
        WHERE ST_Intersects(
            ST_Transform(ST_SetSRID(ST_GeomFromGeoJSON(geom), srid), 4326),
            ST_SetSRID(
                ST_GeomFromGeoJSON('{polygon_geojson}'),
                4326
            )
        );
        """
        df = pd.read_sql(query, conn)
        return df
    except Exception as e:
        print(f"Query error in table {table_name}: {e}")
        return pd.DataFrame()

@app.route('/query_geometries', methods=['POST'])
def query_geometries():
    data = request.json
    polygon = data['polygon']
    dataframes = query_geometries_within_polygon(json.dumps(polygon))
    
    # Convert each dataframe to a dictionary and store in a list
    dataframes_dicts = [df.to_dict(orient='records') for df in dataframes]
    
    return jsonify(dataframes_dicts)

@app.route('/upload_to_arcgis', methods=['POST'])
def upload_to_arcgis():
    data = request.json
    all_dataframes_dicts = data['dataframes']

    # Replace with your ArcGIS Online credentials
    gis = GIS("https://www.arcgis.com", os.getenv("ARCGIS_USERNAME"), os.getenv("ARCGIS_PASSWORD"))

    # Create a WebMap
    webmap = WebMap()

    for df_dict in all_dataframes_dicts:
        df = pd.DataFrame(df_dict)
        sdf = pd.DataFrame.spatial.from_df(df, geometry_column='geometry', sr=3857)
        webmap.add_layer(sdf)

    # Save the webmap
    webmap_item = webmap.save({'title': 'WebMap Title', 'snippet': 'Description of the webmap', 'tags': 'test'})
    
    return jsonify({'status': 'success', 'webmap_url': webmap_item.homepage})

if __name__ == '__main__':
    app.run(debug=True)
