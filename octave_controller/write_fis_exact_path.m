function write_fis_exact_path(fisObj, targetFisPath)
  % splits target path so writefis gets directory + base filename
  [targetDir, targetName, ~] = fileparts(targetFisPath);
  if isempty(targetDir)
    targetDir = '.';
  end
  if ~exist(targetDir, 'dir')
    mkdir(targetDir);
  end

  % writes in target directory, then restores original cwd even on failure
  oldDir = pwd();
  unwind_protect
    cd(targetDir);
    writefis(fisObj, targetName);
  unwind_protect_cleanup
    cd(oldDir);
  end_unwind_protect
end
