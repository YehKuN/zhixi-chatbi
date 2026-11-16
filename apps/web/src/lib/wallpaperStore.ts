/** 工作台壁纸存储：图片/视频以 Blob 形式存入 IndexedDB，避免 localStorage 容量限制。 */

export interface StoredWallpaper {
  blob: Blob;
  kind: "image" | "video";
  name: string;
  updatedAt: number;
}

const DB_NAME = "chatbi.ask";
const DB_VERSION = 1;
const STORE_NAME = "wallpaper";
const RECORD_KEY = "current";

function openDatabase(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DB_NAME, DB_VERSION);
    request.onupgradeneeded = () => {
      const database = request.result;
      if (!database.objectStoreNames.contains(STORE_NAME)) database.createObjectStore(STORE_NAME);
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error ?? new Error("打不开壁纸存储"));
  });
}

function runTransaction<T>(
  mode: IDBTransactionMode,
  run: (store: IDBObjectStore) => IDBRequest<T>,
): Promise<T | null> {
  return openDatabase().then((database) => new Promise<T | null>((resolve, reject) => {
    const transaction = database.transaction(STORE_NAME, mode);
    const request = run(transaction.objectStore(STORE_NAME));
    request.onsuccess = () => resolve((request.result as T | undefined) ?? null);
    request.onerror = () => reject(request.error ?? new Error("壁纸存储操作失败"));
    transaction.oncomplete = () => database.close();
    transaction.onabort = () => {
      database.close();
      reject(transaction.error ?? new Error("壁纸存储事务中断"));
    };
  }));
}

export async function readStoredWallpaper(): Promise<StoredWallpaper | null> {
  if (typeof indexedDB === "undefined") return null;
  try {
    return await runTransaction<StoredWallpaper>("readonly", (store) => store.get(RECORD_KEY));
  } catch {
    return null;
  }
}

export async function saveStoredWallpaper(wallpaper: StoredWallpaper): Promise<boolean> {
  if (typeof indexedDB === "undefined") return false;
  try {
    await runTransaction<IDBValidKey>("readwrite", (store) => store.put(wallpaper, RECORD_KEY));
    return true;
  } catch {
    return false;
  }
}

export async function clearStoredWallpaper(): Promise<void> {
  if (typeof indexedDB === "undefined") return;
  try {
    await runTransaction<undefined>("readwrite", (store) => store.delete(RECORD_KEY));
  } catch {
    // 清理失败时保留内存状态即可，下次覆盖写入。
  }
}
