"""LSTM architecture used by the endpoint benchmark. No data I/O occurs here."""
from sklearn.preprocessing import MinMaxScaler
import tensorflow as tf
from tensorflow.keras.models import Sequential
from tensorflow.keras.layers import LSTM, Dense, Dropout, Input
from tensorflow.keras.optimizers import Adam


class AdsorptionAI:
    """Architecture constructor; workbook loading and historical training are excluded."""
    def __init__(self):
        self.scaler_X = MinMaxScaler()
        self.scaler_y = MinMaxScaler()
        self.model = None

    def build_deep_lstm(self):
        model = Sequential([
            Input(shape=(1, 4)),
            LSTM(128, return_sequences=True, activation="tanh"),
            Dropout(0.2),
            LSTM(64, activation="tanh"),
            Dropout(0.1),
            Dense(32, activation="relu"),
            Dense(16, activation="relu"),
            Dense(1),
        ])
        model.compile(optimizer=Adam(learning_rate=0.001), loss="mse", metrics=["mae"])
        return model
