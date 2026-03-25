function write_prediction_csv(outCsvPath, x, yTrue, yPred)
  % writes prediction rows so we can inspect and plot model output later
  outFid = fopen(outCsvPath, 'w');
  if outFid < 0
    error('Could not open output CSV for writing: %s', outCsvPath);
  end

  fprintf(outFid, 'queue_total_norm,imbalance,target_ns_ratio,predicted_ns_ratio,abs_error\n');
  % keep precision high for stable downstream analysis
  for i = 1:numel(yTrue)
    absErr = abs(yPred(i) - yTrue(i));
    fprintf(outFid, '%.10f,%.10f,%.10f,%.10f,%.10f\n', x(i, 1), x(i, 2), yTrue(i), yPred(i), absErr);
  end

  fclose(outFid);
end
