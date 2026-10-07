(function() {
    try {
        var logFile = new File("C:/Users/L.Thirumala Teja/AI_EDITOR/extendscript_log.txt");
        logFile.open("w");
        logFile.writeln("ExtendScript execution started: " + new Date().toString());

        // 1. Create a new empty project
        app.newProject();
        logFile.writeln("Created new project.");

        // 2. Create the required project-panel folders
        var footageFolder = app.project.items.addFolder("01_FOOTAGE");
        var audioFolder = app.project.items.addFolder("02_AUDIO");
        var mainCompFolder = app.project.items.addFolder("03_MAIN_COMP");
        var adjFolder = app.project.items.addFolder("04_ADJUSTMENTS");
        var exportFolder = app.project.items.addFolder("05_EXPORT");
        logFile.writeln("Created project folders: 01_FOOTAGE, 02_AUDIO, 03_MAIN_COMP, 04_ADJUSTMENTS, 05_EXPORT");

        // 3. Import all extracted video clips from temp_working_footage
        var footageDir = new Folder("C:/Users/L.Thirumala Teja/AI_EDITOR/temp_working_footage");
        var videoFiles = footageDir.getFiles(function(f) {
            return f instanceof File && f.name.match(/\.(mp4|mov|avi|mkv)$/i);
        });

        // Sort video files alphabetically (clip_01, clip_02, etc.)
        videoFiles.sort(function(a, b) {
            return a.name.toLowerCase().localeCompare(b.name.toLowerCase());
        });

        logFile.writeln("Found " + videoFiles.length + " video files.");

        for (var i = 0; i < videoFiles.length; i++) {
            var vFile = videoFiles[i];
            var importOptions = new ImportOptions(vFile);
            if (importOptions.canImportAs(ImportAsType.FOOTAGE)) {
                var importedItem = app.project.importFile(importOptions);
                importedItem.parentFolder = footageFolder;
                logFile.writeln("Imported video: " + vFile.name + " -> 01_FOOTAGE");
            } else {
                logFile.writeln("WARNING: Cannot import as footage: " + vFile.name);
            }
        }

        // 4. Import the supplied MP3 into 02_AUDIO
        var audioFile = new File("C:/Users/L.Thirumala Teja/Downloads/fragment - slowed - slxughter.mp3");
        if (audioFile.exists) {
            var audioImportOptions = new ImportOptions(audioFile);
            if (audioImportOptions.canImportAs(ImportAsType.FOOTAGE)) {
                var importedAudio = app.project.importFile(audioImportOptions);
                importedAudio.parentFolder = audioFolder;
                logFile.writeln("Imported audio: " + audioFile.name + " -> 02_AUDIO");
            } else {
                logFile.writeln("WARNING: Cannot import audio as footage: " + audioFile.name);
            }
        } else {
            logFile.writeln("ERROR: Audio file does not exist: " + audioFile.fsName);
        }

        // 5. Save the project as C:\Users\L.Thirumala Teja\AI_EDITOR\Naruto_Sasuke_Fragment_AMV.aep
        var saveFile = new File("C:/Users/L.Thirumala Teja/AI_EDITOR/Naruto_Sasuke_Fragment_AMV.aep");
        app.project.save(saveFile);
        logFile.writeln("Saved project to: " + saveFile.fsName);
        logFile.writeln("ExtendScript execution finished successfully: " + new Date().toString());
        logFile.close();
    } catch (e) {
        var errFile = new File("C:/Users/L.Thirumala Teja/AI_EDITOR/extendscript_error.txt");
        errFile.open("w");
        errFile.writeln("Error: " + e.toString() + " on line " + e.line);
        errFile.close();
    }
})();
