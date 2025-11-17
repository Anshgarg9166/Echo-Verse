// mobile/app/live/caption.tsx
import React, { useEffect, useRef, useState } from "react";
import { View, Text, Button, Platform, ScrollView } from "react-native";
import { Audio } from "expo-av";
import * as FileSystem from "expo-file-system/legacy";

/**
 * Small, safe session id generator — avoids uuid + crypto issues on Expo
 */
const makeSessionId = () => `${Date.now()}-${Math.floor(Math.random() * 1e9)}`;

// Replace with your PC's IP + port (ensure emulator/device can reach it)
const SERVER_URL = "http://10.11.29.57:8000/api/chunk";
const FLUSH_URL = SERVER_URL.replace("/api/chunk", "/api/flush");

export default function LiveCaption() {
  const [recording, setRecording] = useState<Audio.Recording | null>(null);
  const [isRunning, setIsRunning] = useState(false);
  const [captions, setCaptions] = useState<string[]>([]);
  const [lastResp, setLastResp] = useState<string | null>(null);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);

  const sessionIdRef = useRef<string>(makeSessionId());
  const isRunningRef = useRef<boolean>(false);
  const loopPromiseRef = useRef<Promise<void> | null>(null);

  useEffect(() => {
    // cleanup on unmount: stop any ongoing recording
    return () => {
      isRunningRef.current = false;
      setIsRunning(false);
      if (recording) {
        try {
          recording.stopAndUnloadAsync();
        } catch (e) {
          // ignore
        }
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // record a short clip and return file URI
  const recordClip = async (durationMs = 1500) => {
    try {
      const perms = await Audio.requestPermissionsAsync();
      // perms may be { status, granted } depending on expo version
      const granted =
        // modern shape
        (perms as any).status === "granted" || (perms as any).granted === true;
      if (!granted) {
        console.warn("Microphone permission not granted");
        setStatusMessage("Microphone permission not granted");
        return null;
      }

      await Audio.setAudioModeAsync({
  allowsRecordingIOS: true,
  playsInSilentModeIOS: true,
  interruptionModeAndroid:
    (Audio as any).INTERRUPTION_MODE_ANDROID_DO_NOT_MIX ??
    (Audio as any).INTERRUPTION_MODE_ANDROID_DUCK_OTHERS ??
    1,
  shouldDuckAndroid: false,
  staysActiveInBackground: false,
  playThroughEarpieceAndroid: false, 
});


      const rec = new Audio.Recording();
      await rec.prepareToRecordAsync({
        android: {
          extension: ".m4a",
          outputFormat: Audio.AndroidOutputFormat.MPEG_4,
          audioEncoder: Audio.AndroidAudioEncoder.AAC,
          sampleRate: 16000,
          numberOfChannels: 1,
          bitRate: 128000, // HIGH quality
        },
        ios: {
          extension: ".m4a",
          outputFormat: Audio.IOSOutputFormat.MPEG4AAC,
          audioQuality: Audio.IOSAudioQuality.HIGH,
          sampleRate: 16000,
          numberOfChannels: 1,
          bitRate: 128000, // HIGH quality
        },
        web: {
          mimeType: undefined,
          bitsPerSecond: undefined
        }
      });


      await rec.startAsync();
      // store to state so cleanup can stop it if needed
      setRecording(rec);

      // wait for chunk duration
      await new Promise((r) => setTimeout(r, durationMs));

      // stop and unload
      try {
        await rec.stopAndUnloadAsync();
      } catch (stopErr) {
        // maybe already stopped; ignore
      }
      const uri = rec.getURI();
      // clear recording state (we have the file on disk)
      setRecording(null);
      return uri;
    } catch (e) {
      console.warn("recordClip err", e);
      setStatusMessage("Recording error");
      try {
        if (recording) {
          await recording.stopAndUnloadAsync();
        }
      } catch {}
      setRecording(null);
      return null;
    }
  };

  const uploadChunk = async (fileUri: string) => {
    if (!fileUri) return;
    const form = new FormData();
    const filename = fileUri.split("/").pop() || "chunk.wav";
    // determine mimetype by extension; on Android Expo usually yields .caf or .m4a
    const lower = filename.toLowerCase();
    const fileType =
      lower.endsWith(".m4a") || lower.endsWith(".caf")
        ? "audio/m4a"
        : lower.endsWith(".mp3")
        ? "audio/mpeg"
        : "audio/wav";

    // For Expo, supply uri, name, type
    form.append("file", {
      uri: fileUri,
      name: filename,
      type: fileType,
    } as any);

    form.append("session_id", sessionIdRef.current);

    try {
      setStatusMessage("Uploading chunk...");
      const resp = await fetch(SERVER_URL, {
        method: "POST",
        body: form,
        // Do not set Content-Type; let fetch set boundary
        headers: {
          Accept: "application/json",
        },
      });

      if (!resp.ok) {
        const text = await resp.text();
        console.warn("Chunk upload failed:", resp.status, text);
        setStatusMessage(`Upload failed: ${resp.status}`);
        setLastResp(text);
        return;
      }

      const json = await resp.json();
      console.log("chunk response:", json);
      setLastResp(JSON.stringify(json));
      setStatusMessage("Chunk uploaded");

      if (json.status === "final" && json.transcript) {
        setCaptions((prev) => [...prev, json.transcript]);
      } else {
        // optional: you can display interim transcript if the server provides it
      }
    } catch (e) {
      console.warn("Upload chunk failed", e);
      setStatusMessage("Upload error");
      setLastResp(String(e));
    } finally {
      // delete tmp file to save space; ignore errors
      try {
        await FileSystem.deleteAsync(fileUri, { idempotent: true });
      } catch (err) {
        // ignore
      }
    }
  };

  // flush session buffer on server (testing helper)
  const flushSession = async () => {
    try {
      setStatusMessage("Flushing session...");
      const resp = await fetch(FLUSH_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: sessionIdRef.current }),
      });
      const json = await resp.json();
      console.log("flush response:", json);
      setLastResp(JSON.stringify(json));
      if (json.transcript) {
        setCaptions((prev) => [...prev, json.transcript]);
      }
      setStatusMessage("Flush done");
    } catch (e) {
      console.warn("Flush error", e);
      setStatusMessage("Flush error");
    }
  };

  // Main loop that records short clips and uploads them in sequence
  const startLoop = async () => {
    if (isRunningRef.current) {
      // already running
      return;
    }
    isRunningRef.current = true;
    setIsRunning(true);
    setStatusMessage("Running");

    // store as ref so stopLoop can cancel properly
    const loop = (async () => {
      while (isRunningRef.current) {
        const uri = await recordClip(1400);
        if (uri) {
          // upload and wait
          await uploadChunk(uri);
        } else {
          // brief pause on failure to avoid tight loop
          await new Promise((r) => setTimeout(r, 300));
        }
      }
    })();

    loopPromiseRef.current = loop;
    // Wait for loop to finish (not necessary here)
    try {
      await loop;
    } catch (e) {
      // ignore
    } finally {
      isRunningRef.current = false;
      setIsRunning(false);
      loopPromiseRef.current = null;
      setStatusMessage("Stopped");
    }
  };

  const stopLoop = async () => {
    isRunningRef.current = false;
    setIsRunning(false);
    setStatusMessage("Stopping");
    // if currently recording, stop it gracefully
    try {
      if (recording) {
        await recording.stopAndUnloadAsync();
        setRecording(null);
      }
    } catch (e) {
      // ignore
    }
    // wait for loop to finish if needed
    if (loopPromiseRef.current) {
      try {
        await loopPromiseRef.current;
      } catch {}
      loopPromiseRef.current = null;
    }
    setStatusMessage("Stopped");
  };

  return (
    <ScrollView style={{ flex: 1, padding: 16 }}>
      <View>
        <Text style={{ fontSize: 18, fontWeight: "700" }}>
          Live Caption & Translate (EchoVerse)
        </Text>

        <View style={{ marginVertical: 12 }}>
          <Button
            title={isRunning ? "Stop" : "Start"}
            onPress={() => {
              if (isRunningRef.current) stopLoop();
              else startLoop();
            }}
          />
        </View>

        <View style={{ marginBottom: 10 }}>
          <Button title="Flush session (test)" onPress={flushSession} />
        </View>

        <View style={{ marginVertical: 10 }}>
          <Text style={{ fontWeight: "600" }}>Session ID:</Text>
          <Text selectable>{sessionIdRef.current}</Text>
        </View>

        <View style={{ marginVertical: 8 }}>
          <Text style={{ fontWeight: "600" }}>Status:</Text>
          <Text>{statusMessage ?? "-"}</Text>
        </View>

        <View style={{ marginVertical: 8 }}>
          <Text style={{ fontWeight: "600" }}>Last server response:</Text>
          <Text selectable numberOfLines={6} style={{ color: "#333" }}>
            {lastResp ?? "-"}
          </Text>
        </View>

        <View style={{ marginTop: 12 }}>
          <Text style={{ fontWeight: "600" }}>Captions:</Text>
          {captions.length === 0 ? (
            <Text>- none yet -</Text>
          ) : (
            captions.map((c, i) => (
              <Text key={i} style={{ marginVertical: 6 }}>
                {c}
              </Text>
            ))
          )}
        </View>
      </View>
    </ScrollView>
  );
}
