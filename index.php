
<?php
print "<img src='MPYCbanner.png'>";
print "<h2> Results 22/23 </h2>";

foreach (glob("*.htm") as $file)
print "<div class='fileicon'>
           <a href='$file'>
               <p class='filetext'>$file</p>
           </a>
      </div>";
?>
