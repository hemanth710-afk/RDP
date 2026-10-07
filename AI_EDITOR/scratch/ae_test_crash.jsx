
var output = [];
try {
    app.newProject();
    var footageFile = new File("C:\\Users\\L.Thirumala Teja\\Downloads\\fragment - slowed - slxughter.mp3");
    var importOptions = new ImportOptions(footageFile);
    output.push("Importing MP3...");
    var footage = app.project.importFile(importOptions);
    output.push("Imported MP3: " + footage.name);
    
    var footageFile2 = new File("C:\\Users\\L.Thirumala Teja\\Downloads\\Naruto Vs Sasuke-2x-RIFE-RIFE4.0-120fps.mp4");
    var importOptions2 = new ImportOptions(footageFile2);
    output.push("Importing MP4...");
    var footage2 = app.project.importFile(importOptions2);
    output.push("Imported MP4: " + footage2.name);
} catch (e) {
    output.push("Error: " + e.toString());
}
var out_file = new File("C:\\Users\\L.Thirumala Teja\\AI_EDITOR\\scratch\\out_crash.txt");
out_file.open("w");
out_file.write(output.join("\n"));
out_file.close();

