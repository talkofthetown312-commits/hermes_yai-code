package com.hermespocket.app;

import android.content.ContentProvider;
import android.content.ContentValues;
import android.database.Cursor;
import android.database.MatrixCursor;
import android.net.Uri;
import android.os.ParcelFileDescriptor;
import android.provider.OpenableColumns;
import android.webkit.MimeTypeMap;
import java.io.File;
import java.io.FileNotFoundException;

/** Read-only, per-URI grants for files explicitly shared through the Android chooser. */
public class ExportProvider extends ContentProvider {
    @Override public boolean onCreate() { return true; }
    private File resolve(Uri uri) throws FileNotFoundException {
        try {
            if (!"content".equals(uri.getScheme()) || !(getContext().getPackageName() + ".exports").equals(uri.getAuthority()) || uri.getPathSegments().size() != 1)
                throw new FileNotFoundException("Invalid export URI.");
            String name = uri.getLastPathSegment();
            if (name == null || name.contains("/") || name.contains("\\")) throw new FileNotFoundException("Invalid name.");
            File root = new File(getContext().getCacheDir(), "exports").getCanonicalFile();
            File file = new File(root, name);
            if (!file.getCanonicalFile().getParentFile().equals(root) || !file.isFile() || !file.getAbsolutePath().equals(file.getCanonicalPath()))
                throw new FileNotFoundException("Export not found.");
            return file;
        } catch (java.io.IOException e) { throw new FileNotFoundException("Export not found."); }
    }
    @Override public ParcelFileDescriptor openFile(Uri uri, String mode) throws FileNotFoundException {
        if (!"r".equals(mode)) throw new FileNotFoundException("Read-only export.");
        return ParcelFileDescriptor.open(resolve(uri), ParcelFileDescriptor.MODE_READ_ONLY);
    }
    @Override public String getType(Uri uri) {
        String ext = MimeTypeMap.getFileExtensionFromUrl(uri.toString());
        String type = MimeTypeMap.getSingleton().getMimeTypeFromExtension(ext.toLowerCase(java.util.Locale.ROOT));
        return type == null ? "application/octet-stream" : type;
    }
    @Override public Cursor query(Uri uri, String[] projection, String selection, String[] args, String sort) {
        try {
            File file = resolve(uri);
            String[] columns = projection == null ? new String[]{OpenableColumns.DISPLAY_NAME, OpenableColumns.SIZE} : projection;
            MatrixCursor cursor = new MatrixCursor(columns);
            MatrixCursor.RowBuilder row = cursor.newRow();
            for (String column : columns) {
                if (OpenableColumns.DISPLAY_NAME.equals(column)) row.add(file.getName().length() > 37 ? file.getName().substring(37) : file.getName());
                else if (OpenableColumns.SIZE.equals(column)) row.add(file.length());
                else row.add(null);
            }
            return cursor;
        } catch (FileNotFoundException e) { return null; }
    }
    @Override public Uri insert(Uri uri, ContentValues values) { throw new UnsupportedOperationException("Read only"); }
    @Override public int delete(Uri uri, String where, String[] args) { throw new UnsupportedOperationException("Read only"); }
    @Override public int update(Uri uri, ContentValues values, String where, String[] args) { throw new UnsupportedOperationException("Read only"); }
}
