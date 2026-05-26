import joblib
import numpy as np
from statsmodels.tsa.arima.model import ARIMA
from influxdb import InfluxDBClient
import datetime
import warnings
warnings.filterwarnings('ignore')

# Load models and scalers
temp_model = joblib.load('/home/emw/arima_temperature.pkl')
humid_model = joblib.load('/home/emw/arima_humidity.pkl')
temp_scaler = joblib.load('/home/emw/temp_scaler.pkl')
humid_scaler = joblib.load('/home/emw/humid_scaler.pkl')

# Connect to influxDB
client = InfluxDBClient(host='localhost', port=8086, database='sensor_data')

def get_recent_data():
	# Get last 1000 readings
	temp_result = client.query('SELECT temperature FROM environment ORDER BY time DESC LIMIT 1000')
	humid_result = client.query('SELECT humidity FROM environment ORDER BY time DESC LIMIT 1000')

	temp_data = [item['temperature'] for item in temp_result.get_points()]
	humid_data = [item['humidity'] for item in humid_result.get_points()]

	# reverse to get chronological ordering
	temp_data.reverse()
	humid_data.reverse()

	return temp_data, humid_data

def make_predictions(temp_data, humid_data):
	# normalise
	temp_scaled = temp_scaler.transform(np.array(temp_data).reshape(-1, 1))
	humid_scaled = humid_scaler.transform(np.array(humid_data).reshape(-1, 1))

 	# Fit and forecast 60 steps ahead
	temp_model_fit = ARIMA(temp_scaled.flatten(), order=(1,1,1)).fit()
	humid_model_fit = ARIMA(humid_scaled.flatten(), order=(1,1,1)).fit()

	temp_pred = temp_model_fit.forecast(steps=60)[-1]
	humid_pred = humid_model_fit.forecast(steps=60)[-1]

	# inverse transform
	temp_pred_original = temp_scaler.inverse_transform([[temp_pred]])[0][0]
	humid_pred_original = humid_scaler.inverse_transform([[humid_pred]])[0][0]

	return temp_pred_original, humid_pred_original

def write_predictions(temp_pred, humid_pred):
	# Write predictions 1 hour into the future
	future_time = datetime.datetime.utcnow() + datetime.timedelta(hours = 1)

	json_body = [
		{
			"measurement": "predictions",
			"time": future_time.isoformat(),
			"fields": {
				"temperature_pred": float(temp_pred),
				"humidity_pred": float(humid_pred)
			}
		}
	]
	client.write_points(json_body)
	print(f'Predictions Written: Temp={temp_pred:.2f}C, Humidity={humid_pred:.2f}%')

if __name__ == "__main__":
	print("fetching recent data...")
	temp_data, humid_data = get_recent_data()

	if len(temp_data) < 10:
		print("Not enough data yet, need at least 10 readings")
	else:
		print("Making Predictions...")
		temp_pred, humid_pred = make_predictions(temp_data, humid_data)
		write_predictions(temp_pred, humid_pred)  
