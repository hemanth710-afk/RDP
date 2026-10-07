import sys
import os
import json
from pathlib import Path
from ae_automation.script_runner import AEScriptRunner

ae_path = r"C:\Program Files\Adobe\Adobe After Effects 2022\Support Files\AfterFX.exe"
runner = AEScriptRunner(executable_path=ae_path)

script = r"""
(function() {
    var result = {
        success: false,
        createdFolders: [],
        importedClips: [],
        importedAudio: null,
        savedPath: null,
        projectItems: []
    };

    // 1. Create a new project
    app.newProject();

    // 2. Create the required project folders
    var folders = ["01_FOOTAGE", "02_AUDIO", "03_MAIN_COMP", "04_ADJUSTMENTS", "05_EXPORT"];
    var folderMap = {};
    for (var i = 0; i < folders.length; i++) {
        var folderItem = app.project.items.addFolder(folders[i]);
        folderMap[folders[i]] = folderItem;
        result.createdFolders.push(folders[i]);
    }

    // 3. Import all extracted video clips into 01_FOOTAGE
    var footageFolder = folderMap["01_FOOTAGE"];
    var footageDir = new Folder("C:/Users/L.Thirumala Teja/AI_EDITOR/temp_working_footage");
    var videoFiles = footageDir.getFiles(function(f) {
        return f instanceof File && f.name.match(/\.(mp4|mov|avi|mkv)$/i);
    });

    videoFiles.sort(function(a, b) {
        return a.name.toLowerCase().localeCompare(b.name.toLowerCase());
    });

    for (var j = 0; j < videoFiles.length; j++) {
        var vFile = videoFiles[j];
        var importOpt = new ImportOptions(vFile);
        if (importOpt.canImportAs(ImportAsType.FOOTAGE)) {
            var item = app.project.importFile(importOpt);
            item.parentFolder = footageFolder;
            result.importedClips.push(vFile.name);
        }
    }

    // 4. Import the supplied MP3 into 02_AUDIO
    var audioFolder = folderMap["02_AUDIO"];
    var audioFile = new File("C:/Users/L.Thirumala Teja/Downloads/fragment - slowed - slxughter.mp3");
    if (audioFile.exists) {
        var audioImportOpt = new ImportOptions(audioFile);
        if (audioImportOpt.canImportAs(ImportAsType.FOOTAGE)) {
            var audioItem = app.project.importFile(audioImportOpt);
            audioItem.parentFolder = audioFolder;
            result.importedAudio = audioFile.name;
        }
    }

    // 5. Save the project
    var saveFile = new File("C:/Users/L.Thirumala Teja/AI_EDITOR/Naruto_Sasuke_Fragment_AMV.aep");
    app.project.save(saveFile);
    result.savedPath = saveFile.fsName;
    result.success = true;

    // Collect all project items for verification
    for (var k = 1; k <= app.project.numItems; k++) {
        var pItem = app.project.item(k);
        result.projectItems.push({
            name: pItem.name,
            typeName: pItem.typeName,
            parentFolderName: pItem.parentFolder ? pItem.parentFolder.name : null
        });
    }

    $.writeln(JSON.stringify(result));
})();
"""

output = runner.run(script)
print("RUNNER OUTPUT:")
print(output)
