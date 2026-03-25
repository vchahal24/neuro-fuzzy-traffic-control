function [x, y, rowsUsed] = load_training_xy(csvPath, controllerFilter)
  % opens training csv and validates that it has the required columns
  fid = fopen(csvPath, 'r');
  if fid < 0
    error('Could not open training CSV: %s', csvPath);
  end

  headerLine = fgetl(fid);
  if ~ischar(headerLine)
    fclose(fid);
    error('Training CSV is empty: %s', csvPath);
  end

  headers = strsplit(strtrim(headerLine), ',');
  idxController = find_header_index(headers, 'controller');
  idxQnorm = find_header_index(headers, 'queue_total_norm');
  idxImbalance = find_header_index(headers, 'imbalance');
  idxTarget = find_header_index(headers, 'target_ns_ratio');

  % collect valid rows into vectors first, then build matrix at the end
  qnormVals = [];
  imbalanceVals = [];
  targetVals = [];

  % parse row-by-row so malformed rows can be skipped safely
  while true
    line = fgetl(fid);
    if ~ischar(line)
      break;
    end
    if isempty(strtrim(line))
      continue;
    end

    parts = strsplit(line, ',');
    if numel(parts) < numel(headers)
      continue;
    end

    rowController = strtrim(parts{idxController});
    if ~isempty(controllerFilter) && ~strcmp(rowController, controllerFilter)
      continue;
    end

    rowQnorm = str2double(parts{idxQnorm});
    rowImbalance = str2double(parts{idxImbalance});
    rowTarget = str2double(parts{idxTarget});

    % skip rows with non-numeric feature or target values
    if any(isnan([rowQnorm, rowImbalance, rowTarget]))
      continue;
    end

    qnormVals(end + 1, 1) = rowQnorm; %#ok<AGROW>
    imbalanceVals(end + 1, 1) = rowImbalance; %#ok<AGROW>
    targetVals(end + 1, 1) = rowTarget; %#ok<AGROW>
  end

  fclose(fid);

  if isempty(targetVals)
    error('No valid rows found in CSV after filtering.');
  end

  % x has two model inputs: [queue_total_norm, imbalance]
  x = [qnormVals, imbalanceVals];
  y = targetVals;
  rowsUsed = numel(y);
end
