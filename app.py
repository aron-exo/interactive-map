from flask import Flask, request, jsonify
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv
import os
import json
from arcgis.gis import GIS
from arcgis.features import SpatialDataFrame

app = Flask(__name__)

# Load environment variables
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

# Query geometries within a polygon for all relevant tables
def query_geometries_within_polygon(polygon_geojson):
    conn = connect_to_database()
    if conn is None:
        return []

    tables = get_tables_with_shape_column(conn)
    all_geometries = []

    for table in tables:
        geometries = query_geometries_from_table(conn, table, polygon_geojson)
        if geometries:
            all_geometries.extend(geometries)

    conn.close()
    return all_geometries

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
        SELECT ST_AsGeoJSON(geom) as geometry
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
        return df['geometry'].tolist()
    except Exception as e:
        print(f"Query error in table {table_name}: {e}")
        return []

@app.route('/query_geometries', methods=['POST'])
def query_geometries():
    data = request.json
    polygon = data['polygon']
    geometries = query_geometries_within_polygon(json.dumps(polygon))
    return jsonify(geometries)

@app.route('/upload_to_arcgis', methods=['POST'])
def upload_to_arcgis():
    data = request.json
    geometries = data['geometries']

    # Replace with your ArcGIS Online credentials
    gis = GIS("https://www.arcgis.com", os.getenv("ARCGIS_USERNAME"), os.getenv("ARCGIS_PASSWORD"))

    # Create a folder for the new layers
    gis.content.create_folder('MyGeometries')

    for table, geoms in geometries.items():
        sdata = SpatialDataFrame.from_features(geoms)
        sdata.spatial.set_geometry('SHAPE')
        sdata.spatial.to_featurelayer(title=table, gis=gis, folder='MyGeometries')

    return jsonify({'status': 'success'})

if __name__ == '__main__':
    app.run(debug=True)
