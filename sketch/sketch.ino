#include <Arduino_RouterBridge.h>
#include <SPI.h>
#include <MFRC522.h>

#define RST_PIN 9
#define SS_PIN 10
MFRC522 rfid(SS_PIN, RST_PIN);

void setup() {
    Bridge.begin();
    Monitor.begin();
    SPI.begin();
    rfid.PCD_Init();
    Monitor.println("RFID reader ready.");
}

void loop() {
    if (!rfid.PICC_IsNewCardPresent() || !rfid.PICC_ReadCardSerial()) {
        delay(100);
        return;
    }

    String tag = "";
    for (byte i = 0; i < rfid.uid.size; i++) {
        if (rfid.uid.uidByte[i] < 0x10) tag += "0";
        tag += String(rfid.uid.uidByte[i], HEX);
    }
    tag.toUpperCase();

    Monitor.print("Scanned tag: ");
    Monitor.println(tag);

    Bridge.call("rfid_scan", tag);  // must match Bridge.provide name in Python

    rfid.PICC_HaltA();
    rfid.PCD_StopCrypto1();
    delay(1000);
}